"""管理員後台：聽說讀寫題庫的新增、編輯、刪除。

路由掛在 admin.py 的 /admin 底下，沿用同一組管理員密碼。資料存取都走 bank_store，
原始題庫檔不會被改動（原因見 bank_store.py 開頭）。

題號規則：後台存檔時依題目在頁面上的順序，把整回測驗重新編成連續題號，
所以管理員新增、刪除題目都不用自己算題號；題組的「Questions 1–6」也會一起更新。
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

import admin as core
import bank_store
import speaking_bank
import writing_bank

bp = core.bp
login_required = core.login_required

SECTION_INFO = {
    'listening': {'name': '聽力', 'icon': 'headphones', 'unit': 'Part'},
    'reading': {'name': '閱讀', 'icon': 'book-open', 'unit': '文章'},
    'writing': {'name': '寫作', 'icon': 'pen', 'unit': 'Task'},
    'speaking': {'name': '口說', 'icon': 'mic', 'unit': '題目'},
}
SPEAKERS = {'narrator': '旁白', 'f1': '女聲 1（英）', 'f2': '女聲 2（英）', 'f3': '女聲 3（澳）', 'f4': '女聲 4（紐）',
            'm1': '男聲 1（英）', 'm2': '男聲 2（愛爾蘭）', 'm3': '男聲 3（紐）', 'm4': '男聲 4（澳）'}
GROUP_TYPES = {
    'listening': {'gapfill': '填空', 'mcq': '單選', 'matching': '配對', 'map': '地圖'},
    'reading': {'tfng': 'TRUE / FALSE / NOT GIVEN', 'ynng': 'YES / NO / NOT GIVEN', 'mcq': '單選',
                'matching': '配對', 'headings': '段落標題', 'gapfill': '填空'},
}
JUDGE = {'tfng': ['TRUE', 'FALSE', 'NOT GIVEN'], 'ynng': ['YES', 'NO', 'NOT GIVEN']}
GAP_RE = re.compile(r'\{(\d+)\}')
RANGE_RE = re.compile(r'Questions?\s+\d+(?:\s*[–-]\s*\d+)?')
TOTAL_QUESTIONS = 40        # 正式雅思聽力、閱讀每回 40 題，成績換算也以 40 題為準


def _section_or_404(section):
    if section not in SECTION_INFO:
        abort(404, description='沒有這個題庫')
    return section


def _test_or_404(section, key):
    _section_or_404(section)
    test = bank_store.find_test(section, key)
    if not test:
        abort(404, description='找不到這份測驗')
    return test


def _tool(name):
    """載入 tools/ 底下的檢查腳本，後台和命令列用同一套比對規則。"""
    path = os.path.join(bank_store.BASE, 'tools', f'{name}.py')
    spec = importlib.util.spec_from_file_location(f'_bank_{name}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_listening = _tool('check_listening')


# ---------------------------------------------------------------- 題號

def _gap_nos(g):
    nos = []
    for r in g.get('rows', []):
        nos += [int(n) for n in GAP_RE.findall(r.get('text', ''))]
    for s in g.get('sections', []):
        for line in s.get('lines', []):
            nos += [int(n) for n in GAP_RE.findall(line)]
    return nos


def group_nos(g):
    return _gap_nos(g) if g['type'] == 'gapfill' else [it['no'] for it in g.get('items', [])]


def doc_nos(part):
    return [n for g in part.get('groups', []) for n in group_nos(g)]


def _range_label(nos):
    if len(nos) == 1:
        return f'Question {nos[0]}'
    return f'Questions {nos[0]}–{nos[-1]}'


def renumber_part(part, start):
    """依頁面順序把題號重編成 start 起的連續號碼，回傳下一個可用題號。"""
    order = doc_nos(part)
    mapping = {old: start + i for i, old in enumerate(order)}
    swap = lambda text: GAP_RE.sub(lambda m: '{%d}' % mapping.get(int(m.group(1)), int(m.group(1))), text)
    for g in part.get('groups', []):
        nos = [mapping[n] for n in group_nos(g)]
        if g['type'] == 'gapfill':
            for r in g.get('rows', []):
                r['text'] = swap(r.get('text', ''))
            for s in g.get('sections', []):
                s['lines'] = [swap(line) for line in s.get('lines', [])]
        else:
            for it in g.get('items', []):
                it['no'] = mapping[it['no']]
        if nos:
            label = _range_label(nos)
            g['range'] = label
            for field in ('instruction', 'limit'):
                if g.get(field):
                    g[field] = RANGE_RE.sub(label, g[field])
    questions = [q for q in part.get('questions', []) if q['no'] in mapping]
    for q in questions:
        q['no'] = mapping[q['no']]
    part['questions'] = sorted(questions, key=lambda q: q['no'])
    if order:
        label = _range_label([start, start + len(order) - 1])
        part['instructions'] = RANGE_RE.sub(label, part.get('instructions') or '') or label
    return start + len(order)


def part_names(section, key):
    pattern = {'listening': r'part\d+\.json', 'reading': r'passage\d+\.json'}[section]
    found = [n for n in bank_store.names(section, key) if re.fullmatch(pattern, n)]
    return sorted(found, key=lambda n: int(re.search(r'\d+', n).group()))


def renumber_test(section, key):
    """整回重新編號；有檔案因此改變就寫回去。"""
    start = 1
    for name in part_names(section, key):
        part = bank_store.read(section, key, name)
        start = renumber_part(part, start)
        bank_store.write(section, key, name, part)
    return start - 1


# ---------------------------------------------------------------- 整理管理員送來的資料

def _text(value):
    return str(value if value is not None else '').strip()


def _texts(values):
    return [t for t in (_text(v) for v in (values or [])) if t]


def _clean_options(options):
    if isinstance(options, list):
        return _texts(options)
    return {_text(k): _text(v) for k, v in (options or {}).items()}


def _clean_group(section, g):
    kind = g['type']
    if kind not in GROUP_TYPES[section]:
        raise ValueError(f'不認得的題型 {kind}')
    out = dict(g)
    for field in ('range', 'instruction', 'limit', 'title', 'optionsTitle'):
        if field in out:
            out[field] = _text(out[field])
    if 'options' in out:
        out['options'] = _clean_options(out['options'])
    if kind == 'gapfill':
        if 'rows' in out:
            out['rows'] = [dict(r, text=_text(r.get('text'))) for r in out['rows'] if _text(r.get('text'))]
        if 'sections' in out:
            out['sections'] = [{'heading': _text(s.get('heading')), 'lines': _texts(s.get('lines'))}
                               for s in out['sections'] if _texts(s.get('lines'))]
    else:
        items = []
        for it in out.get('items', []):
            item = dict(it, no=int(it['no']))
            if kind == 'mcq':
                item['stem'] = _text(it.get('stem'))
                item['options'] = _clean_options(it.get('options'))
            else:
                item['text'] = _text(it.get('text'))
            items.append(item)
        out['items'] = items
    return out


def _clean_questions(questions):
    return [{'no': int(q['no']), 'answers': _texts(q.get('answers')), 'explain': _text(q.get('explain')),
             'quote': _text(q.get('quote'))} for q in questions]


def _clean_part(section, data, old):
    out = {'no': old['no'], 'context': _text(data.get('context')), 'instructions': _text(data.get('instructions')),
           'groups': [_clean_group(section, g) for g in data.get('groups', [])],
           'questions': _clean_questions(data.get('questions', []))}
    if section == 'listening':
        out['audio'] = old['audio']
        cues = []
        for c in data.get('cues', []):
            v, t = _text(c.get('v')), _text(c.get('t'))
            if t:
                cues.append({'v': v, 't': t})
        out['cues'] = cues
    else:
        out['title'] = _text(data.get('title'))
        out['paragraphs'] = [{'label': _text(p.get('label')), 'text': _text(p.get('text'))}
                             for p in data.get('paragraphs', []) if _text(p.get('text'))]
    return out


def _number(value, label):
    try:
        n = float(str(value).strip())
    except ValueError:
        raise ValueError(f'「{label}」要填數字') from None
    return int(n) if n == int(n) else n


def _clean_chart(c):
    series = [{'name': _text(s.get('name')), 'values': [_number(v, '數據') for v in s.get('values', [])]}
              for s in c.get('series', []) if _text(s.get('name'))]
    return {'type': 'bar' if c.get('type') == 'bar' else 'line', 'title': _text(c.get('title')),
            'x': _texts(c.get('x')), 'y_label': _text(c.get('y_label')),
            'y_max': _number(c.get('y_max'), 'Y 軸最大值'), 'y_step': _number(c.get('y_step'), 'Y 軸間隔'),
            'series': series}


def _clean_task(data, old):
    out = {'no': old['no'], 'minutes': int(_number(data.get('minutes'), '建議時間')),
           'min_words': int(_number(data.get('min_words'), '最少字數')),
           'prompt': str(data.get('prompt') or '').strip(), 'instruction': _text(data.get('instruction'))}
    if data.get('chart'):
        out['chart'] = _clean_chart(data['chart'])
    return out


def _clean_speaking(data):
    p2 = data.get('part2') or {}
    return {
        'title': _text(data.get('title')),
        'part1': [{'topic': _text(t.get('topic')), 'questions': _texts(t.get('questions'))}
                  for t in data.get('part1', [])],
        'part2': {'topic': _text(p2.get('topic')), 'cue': _text(p2.get('cue')), 'points': _texts(p2.get('points')),
                  'final': _text(p2.get('final')), 'followups': _texts(p2.get('followups'))},
        'part3': [{'theme': _text(t.get('theme')), 'questions': _texts(t.get('questions'))}
                  for t in data.get('part3', [])],
    }


def clean(section, name, data, old):
    if section in ('listening', 'reading'):
        return _clean_part(section, data, old)
    if section == 'writing':
        return _clean_task(data, old)
    return _clean_speaking(data)


# ---------------------------------------------------------------- 檢查

def _allowed_answers(g, item=None):
    """這一題可以選的答案；None 代表自由填寫。"""
    kind = g['type']
    if kind in JUDGE:
        return set(JUDGE[kind])
    if kind == 'mcq':
        return set(item.get('options', {}))
    if kind in ('matching', 'headings', 'map'):
        return set(g.get('options', []))
    return set(g['options']) if g.get('options') else None


def check_part(section, part, require_content):
    """回傳 (errors, warnings)。errors 會擋住存檔，warnings 只提醒。"""
    errors, warnings = [], []
    unit = '段逐字稿' if section == 'listening' else '段文章'
    if section == 'listening':
        source = ' '.join(c['t'] for c in part['cues'] if c['v'] != 'pause')
        for i, c in enumerate(part['cues'], 1):
            if c['v'] == 'pause':
                try:
                    float(c['t'])
                except ValueError:
                    errors.append(f'逐字稿第 {i} 行：停頓要填秒數')
            elif c['v'] not in SPEAKERS:
                errors.append(f'逐字稿第 {i} 行：請選說話者')
    else:
        source = ' '.join(p['text'] for p in part['paragraphs'])
    if require_content and not source.strip():
        errors.append(f'還沒有內容：請至少填一{unit}')

    order = doc_nos(part)
    questions = {q['no']: q for q in part['questions']}
    if len(set(order)) != len(order):
        errors.append('同一個空格題號出現兩次，請刪掉重複的空格')
    if set(order) != set(questions):
        errors.append('題目和答案對不起來，請重新整理頁面再改一次')
    if require_content and not order:
        errors.append('這一部分至少要有一題')

    allowed = {}
    for gi, g in enumerate(part['groups'], 1):
        where = f'題組 {gi}'
        if not group_nos(g):
            errors.append(f'{where}：沒有任何題目（填空題請用「插入空格」加上空格）')
        if g['type'] in ('matching', 'headings'):
            if len(g.get('options', {})) < 2:
                errors.append(f'{where}：選項至少要兩個')
            if not all(g.get('options', {}).values()):
                errors.append(f'{where}：有選項還沒填內容')
        if g['type'] == 'gapfill':
            for n in _gap_nos(g):
                allowed[n] = _allowed_answers(g)
        else:
            for it in g.get('items', []):
                allowed[it['no']] = _allowed_answers(g, it)
                label = f'{where} 第 {it["no"]} 題'
                if not (it.get('stem') if g['type'] == 'mcq' else it.get('text')):
                    errors.append(f'{label}：題目還沒填')
                if g['type'] == 'mcq':
                    if len(it.get('options', {})) < 2:
                        errors.append(f'{label}：選項至少要兩個')
                    if not all(it.get('options', {}).values()):
                        errors.append(f'{label}：有選項還沒填內容')

    plain = check_listening.normalise(source)
    for no in order:
        q = questions.get(no)
        if not q:
            continue
        label = f'第 {no} 題'
        if not q['answers']:
            errors.append(f'{label}：還沒填答案')
            continue
        valid = allowed.get(no)
        if valid is not None:
            bad = [a for a in q['answers'] if a not in valid]
            if bad:
                errors.append(f'{label}：答案「{bad[0]}」不是這題的選項')
        elif source.strip() and not any(check_listening.answer_in_transcript(a, source) for a in q['answers']):
            where = '逐字稿' if section == 'listening' else '文章'
            warnings.append(f'{label}：答案在{where}裡找不到，請確認有沒有打錯')
        if not q['explain']:
            warnings.append(f'{label}：還沒寫解析')
        # 聽力的引句可能跨兩個人的台詞，和 check_listening 一樣只比對開頭
        quote = q['quote'][:40] if section == 'listening' else q['quote']
        if section == 'listening' and valid is None:
            quote = ''      # 聽力填空題已經用答案本身比對過逐字稿
        if quote and source.strip() and check_listening.normalise(quote) not in plain:
            warnings.append(f'{label}：引用的原文在{"逐字稿" if section == "listening" else "文章"}裡找不到')
    return errors, warnings


def check_task(task, require_content):
    errors = []
    if require_content and not task['prompt']:
        errors.append(f'Task {task["no"]}：題目還沒填')
    if task['minutes'] <= 0 or task['min_words'] <= 0:
        errors.append(f'Task {task["no"]}：時間和字數要大於 0')
    c = task.get('chart')
    if c and (require_content or c['x'] or c['series']):      # 草稿的空白圖表先不檢查
        if not c['x']:
            errors.append('圖表：X 軸項目還沒填')
        if not c['series']:
            errors.append('圖表：至少要一組數據')
        if c['y_max'] <= 0 or c['y_step'] <= 0 or c['y_max'] / c['y_step'] > 50:
            errors.append('圖表：Y 軸最大值和間隔要大於 0，刻度不能超過 50 格')
        for s in c['series']:
            if len(s['values']) != len(c['x']):
                errors.append(f'圖表「{s["name"]}」：數據有 {len(s["values"])} 個，X 軸有 {len(c["x"])} 個，數量要一樣')
        if not errors:
            try:
                writing_bank.chart_svg(c)
            except (KeyError, TypeError, ValueError, ZeroDivisionError) as e:
                errors.append(f'圖表畫不出來：{e}')
    return errors, []


def check_speaking(t, require_content):
    errors = []
    for label, items, field in (('Part 1', t['part1'], 'topic'), ('Part 3', t['part3'], 'theme')):
        for i, item in enumerate(items, 1):
            if not item[field]:
                errors.append(f'{label} 第 {i} 個話題：還沒填名稱')
            if not item['questions']:
                errors.append(f'{label} 第 {i} 個話題：至少要一個問題')
        if require_content and not items:
            errors.append(f'{label}：至少要一個話題')
    if require_content and not (t['part2']['cue'] and t['part2']['points']):
        errors.append('Part 2：題卡題目和 You should say 要點都要填')
    if not errors and require_content:
        try:
            speaking_bank.build_steps(t)
        except (KeyError, TypeError, ValueError, IndexError) as e:
            errors.append(f'口說流程組不起來：{e}')
    return errors, []


def check_file(section, data, require_content):
    if section in ('listening', 'reading'):
        return check_part(section, data, require_content)
    if section == 'writing':
        return check_task(data, require_content)
    return check_speaking(data, require_content)


def file_names(section, key):
    if section in ('listening', 'reading'):
        return part_names(section, key)
    if section == 'writing':
        return [n for n in bank_store.names(section, key) if re.fullmatch(r'task\d+\.json', n)]
    return ['test.json']


def file_label(section, name, data):
    if section == 'listening':
        return f'Part {data["no"]}', data.get('context', '')
    if section == 'reading':
        return f'文章 {data["no"]}', data.get('title', '')
    if section == 'writing':
        return f'Task {data["no"]}', (data.get('prompt') or '')[:70]
    return '全部題目', 'Part 1、Part 2、Part 3'


def question_count(section, data):
    if section in ('listening', 'reading'):
        return len(data['questions'])
    if section == 'writing':
        return 1
    return sum(len(t['questions']) for t in data['part1'] + data['part3']) + (1 if data['part2'].get('cue') else 0)


# ---------------------------------------------------------------- 聽力音檔

_audio_jobs = {}


def audio_rows(key):
    rows = []
    for name in part_names('listening', key):
        part = bank_store.read('listening', key, name)
        exists = os.path.exists(os.path.join(bank_store.BASE, 'static', 'audio', 'listening', part['audio']))
        stale = bool(part['cues']) and (not exists or bank_store.audio_stale(key, name, part['cues']))
        rows.append({'no': part['no'], 'name': name, 'exists': exists, 'stale': stale, 'empty': not part['cues']})
    return rows


def _audio_log(key):
    return os.path.join(bank_store.EDIT_DIR, f'_audio_{key}.log')


def _make_audio(key, nos):
    tool = os.path.join(bank_store.BASE, 'tools', 'make_listening_audio.py')
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    failed = False
    os.makedirs(bank_store.EDIT_DIR, exist_ok=True)
    with open(_audio_log(key), 'w', encoding='utf-8') as log:
        for no in nos:
            code = subprocess.run([sys.executable, tool, key, str(no), '--force'], stdout=log,
                                  stderr=subprocess.STDOUT, cwd=bank_store.BASE, env=env,
                                  creationflags=flags).returncode
            failed = failed or code != 0
    _audio_jobs[key] = {'running': False, 'failed': failed}


# ---------------------------------------------------------------- 頁面：總覽

@bp.route('/bank/')
@login_required
def bank_home():
    columns = []
    for section, info in SECTION_INFO.items():
        items = bank_store.all_tests(section)
        columns.append(dict(info, key=section, tests=[t for t in items if not t['trash']],
                            trash=[t for t in items if t['trash']]))
    return render_template('admin/bank_home.html', columns=columns)


def _blank_files(section, key, title):
    if section == 'listening':
        files = {f'part{n}.json': {'no': n, 'context': '', 'audio': f'{key}_part{n}.mp3', 'instructions': '',
                                   'cues': [], 'groups': [], 'questions': []} for n in range(1, 5)}
        files['meta.json'] = {'title': title, 'subtitle': 'Parts 1–4，共 40 題，約 30 分鐘'}
    elif section == 'reading':
        files = {f'passage{n}.json': {
            'no': n, 'title': '', 'context': '',
            'instructions': f'You should spend about 20 minutes on <b>Questions 1–13</b>, which are based on Reading Passage {n} below.',
            'paragraphs': [], 'groups': [], 'questions': []} for n in range(1, 4)}
        files['meta.json'] = {'title': title, 'subtitle': 'Academic Reading，3 篇文章共 40 題，60 分鐘'}
    elif section == 'writing':
        files = {
            'task1.json': {'no': 1, 'minutes': 20, 'min_words': 150, 'prompt': '',
                           'instruction': 'Summarise the information by selecting and reporting the main features, and make comparisons where relevant.',
                           'chart': {'type': 'line', 'title': '', 'x': [], 'y_label': '', 'y_max': 100, 'y_step': 10, 'series': []}},
            'task2.json': {'no': 2, 'minutes': 40, 'min_words': 250, 'prompt': '',
                           'instruction': 'Give reasons for your answer and include any relevant examples from your own knowledge or experience.'},
            'meta.json': {'title': title, 'module': 'Academic'},
        }
    else:
        files = {'test.json': {'title': title, 'part1': [], 'part3': [],
                               'part2': {'topic': '', 'cue': '', 'points': [], 'final': '', 'followups': []}}}
    return files


@bp.route('/bank/<section>/new', methods=['POST'])
@login_required
def bank_new(section):
    _section_or_404(section)
    title = _text(request.form.get('title'))[:80]
    if not title:
        flash('請先填這份測驗的名稱', 'warn')
        return redirect(url_for('admin.bank_home'))
    key = bank_store.add_test(section, title, _text(request.form.get('topics'))[:200],
                              lambda k: _blank_files(section, k, title))
    flash(f'已建立草稿「{title}」，題目填好後按「上架」學生才看得到')
    return redirect(url_for('admin.bank_test', section=section, key=key))


# ---------------------------------------------------------------- 頁面：一份測驗

@bp.route('/bank/<section>/<key>/')
@login_required
def bank_test(section, key):
    test = _test_or_404(section, key)
    files, total, problems = [], 0, 0
    for name in file_names(section, key):
        data = bank_store.read(section, key, name)
        if data is None:
            continue
        errors, warnings = check_file(section, data, True)
        title, sub = file_label(section, name, data)
        count = question_count(section, data)
        total += count
        problems += len(errors)
        files.append({'name': name, 'title': title, 'sub': sub, 'count': count, 'errors': errors,
                      'warnings': warnings, 'edited': bank_store.is_edited(section, key, name),
                      'can_revert': bank_store.is_edited(section, key, name)
                      and bank_store.read_original(section, key, name) is not None})
    audio = audio_rows(key) if section == 'listening' else []
    job = _audio_jobs.get(key, {})
    log = ''
    if job.get('failed'):
        try:
            with open(_audio_log(key), encoding='utf-8') as f:
                log = ''.join(f.readlines()[-6:])
        except OSError:
            log = ''
    meta = bank_store.read(section, key, 'meta.json', {}) or {}
    return render_template('admin/bank_test.html', section=section, info=SECTION_INFO[section], test=test,
                           files=files, total=total, problems=problems, audio=audio, job=job, log=log,
                           subtitle=meta.get('subtitle', ''), need_total=TOTAL_QUESTIONS
                           if section in ('listening', 'reading') else None)


@bp.route('/bank/<section>/<key>/info', methods=['POST'])
@login_required
def bank_info(section, key):
    _test_or_404(section, key)
    title = _text(request.form.get('title'))[:80]
    if not title:
        flash('測驗名稱不能空白', 'warn')
        return redirect(url_for('admin.bank_test', section=section, key=key))
    bank_store.set_info(section, key, title, _text(request.form.get('topics'))[:200])
    if section == 'speaking':
        data = bank_store.read(section, key, 'test.json')
        data['title'] = title
        bank_store.write(section, key, 'test.json', data)
    else:
        meta = bank_store.read(section, key, 'meta.json', {}) or {}
        meta['title'] = title
        if 'subtitle' in request.form:
            meta['subtitle'] = _text(request.form.get('subtitle'))[:120]
        bank_store.write(section, key, 'meta.json', meta)
    flash('已更新測驗資訊')
    return redirect(url_for('admin.bank_test', section=section, key=key))


@bp.route('/bank/<section>/<key>/publish', methods=['POST'])
@login_required
def bank_publish(section, key):
    _test_or_404(section, key)
    problems = []
    for name in file_names(section, key):
        title = file_label(section, name, bank_store.read(section, key, name))[0]
        problems += [f'{title}：{e}' for e in check_file(section, bank_store.read(section, key, name), True)[0]]
    if problems:
        flash('還不能上架：' + '；'.join(problems[:6]) + ('……' if len(problems) > 6 else ''), 'warn')
    else:
        bank_store.set_draft(section, key, False)
        flash('已上架，學生現在看得到這份測驗了')
    return redirect(url_for('admin.bank_test', section=section, key=key))


@bp.route('/bank/<section>/<key>/unpublish', methods=['POST'])
@login_required
def bank_unpublish(section, key):
    _test_or_404(section, key)
    bank_store.set_draft(section, key, True)
    flash('已下架成草稿，學生暫時看不到，舊成績都還在')
    return redirect(url_for('admin.bank_test', section=section, key=key))


@bp.route('/bank/<section>/<key>/trash', methods=['POST'])
@login_required
def bank_trash(section, key):
    test = _test_or_404(section, key)
    bank_store.set_trash(section, key, True)
    flash(f'已把「{test["title"]}」移到回收區（學生的成績都保留，隨時可以救回）')
    return redirect(url_for('admin.bank_home'))


@bp.route('/bank/<section>/<key>/restore', methods=['POST'])
@login_required
def bank_restore(section, key):
    test = _test_or_404(section, key)
    bank_store.set_trash(section, key, False)
    flash(f'已救回「{test["title"]}」')
    return redirect(url_for('admin.bank_test', section=section, key=key))


@bp.route('/bank/<section>/<key>/audio', methods=['POST'])
@login_required
def bank_audio(section, key):
    _test_or_404(section, key)
    if section != 'listening':
        abort(404)
    if _audio_jobs.get(key, {}).get('running'):
        flash('音檔正在產生中，請稍候', 'warn')
    else:
        nos = [r['no'] for r in audio_rows(key) if r['stale']]
        if nos:
            _audio_jobs[key] = {'running': True}
            threading.Thread(target=_make_audio, args=(key, nos), daemon=True).start()
            flash(f'開始產生 {len(nos)} 個音檔，每個約需 1 分鐘，可以先做別的事')
    return redirect(url_for('admin.bank_test', section=section, key=key))


# ---------------------------------------------------------------- 頁面：編輯題目

def _file_or_404(section, key, name):
    _test_or_404(section, key)
    if name not in file_names(section, key):
        abort(404, description='找不到這個檔案')
    data = bank_store.read(section, key, name)
    if data is None:
        abort(404, description='找不到這個檔案')
    return data


@bp.route('/bank/<section>/<key>/edit/<name>', methods=['GET', 'POST'])
@login_required
def bank_edit(section, key, name):
    old = _file_or_404(section, key, name)
    draft = bank_store.is_draft(section, key)
    if request.method == 'POST':
        try:
            data = clean(section, name, json.loads(request.form.get('data') or '{}'), old)
            errors, warnings = check_file(section, data, not draft)
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            return jsonify(ok=False, errors=[f'資料格式不對：{e}'])
        if errors:
            return jsonify(ok=False, errors=errors)
        bank_store.write(section, key, name, data)
        if section in ('listening', 'reading'):
            total = renumber_test(section, key)
            if not draft and total != TOTAL_QUESTIONS:
                flash(f'提醒：這回現在共 {total} 題，正式考試是 {TOTAL_QUESTIONS} 題，成績換算的 Band 會不準', 'warn')
            if section == 'listening' and data['cues'] != old['cues']:
                flash('逐字稿改過了，請回到測驗頁按「重新產生音檔」，學生才會聽到新內容', 'warn')
        flash('已儲存，學生重新整理頁面就會看到')
        for w in warnings[:8]:
            flash(w, 'warn')
        return jsonify(ok=True, redirect=url_for('admin.bank_edit', section=section, key=key, name=name))
    title, sub = file_label(section, name, old)
    config = {'section': section, 'name': name, 'speakers': SPEAKERS, 'types': GROUP_TYPES.get(section, {}),
              'judge': JUDGE, 'saveUrl': url_for('admin.bank_edit', section=section, key=key, name=name)}
    return render_template('admin/bank_edit.html', section=section, info=SECTION_INFO[section],
                           test=bank_store.find_test(section, key), title=title, sub=sub, data=old, config=config)


@bp.route('/bank/<section>/<key>/revert/<name>', methods=['POST'])
@login_required
def bank_revert(section, key, name):
    _file_or_404(section, key, name)
    if bank_store.revert(section, key, name):
        if section in ('listening', 'reading'):
            renumber_test(section, key)
        flash('已還原成原本的題目')
    return redirect(url_for('admin.bank_test', section=section, key=key))
