from flask import Flask, request, render_template, redirect, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quiz.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    enrolled_course = db.Column(db.String(50))

class Vocabulary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False)
    level = db.Column(db.String(20), nullable=False) # 基礎級/中級/中高級/進階級
    theme = db.Column(db.String(50), nullable=False) # 【新增】20大主題或6大模組
    word = db.Column(db.String(100), nullable=False)
    meaning = db.Column(db.String(200), nullable=False)
    sentence = db.Column(db.String(500))

class LearningProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    vocab_id = db.Column(db.Integer, db.ForeignKey('vocabulary.id'), nullable=False)
    status = db.Column(db.String(20), default='unfamiliar')
    last_reviewed = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

@app.route('/login')
def login_redirect():
    token = request.args.get('token')
    student = Student.query.filter_by(token=token).first()
    if student:
        return redirect(f'/dashboard/{student.id}')
    return "無效的帳號或 Token，請從補習班系統重新進入。"

@app.route('/dashboard/<int:student_id>')
def dashboard(student_id):
    student = Student.query.get(student_id)
    if not student: return "找不到學生資料"
    unlocked_count = LearningProgress.query.filter_by(student_id=student_id, status='familiar').count()
    return render_template('dashboard.html', student=student, unlocked_count=unlocked_count)

@app.route('/vocab_themes/<int:student_id>')
def vocab_themes(student_id):
    student = Student.query.get(student_id)
    if not student: return "找不到學生資料"
    
    themes = [
        {"id": "01", "name": "01 教育與職涯", "desc": "教育制度、學術研究、就業、職場發展", "icon": "🎓"},
        {"id": "02", "name": "02 環境與自然生態", "desc": "氣候變遷、環境污染、能源、動物保育", "icon": "🌍"},
        {"id": "03", "name": "03 科技與科學", "desc": "人工智慧、數位科技、科學研究、創新", "icon": "🔬"},
        {"id": "04", "name": "04 健康與心理", "desc": "醫療、公共衛生、心理健康、人類行為", "icon": "🏥"},
        {"id": "05", "name": "05 社會與文化", "desc": "社會議題、文化差異、家庭、全球化", "icon": "🤝"},
        {"id": "06", "name": "06 經濟與商業", "desc": "經濟發展、金融、消費、企業經營", "icon": "💰"},
        {"id": "07", "name": "07 政府與法律", "desc": "公共政策、社會福利、犯罪、司法制度", "icon": "⚖️"},
        {"id": "08", "name": "08 城市與交通", "desc": "都市化、住房、交通、公共建設", "icon": "🏙️"},
        {"id": "09", "name": "09 媒體與藝術", "desc": "新聞、廣告、社群媒體、藝術娛樂", "icon": "🎨"},
        {"id": "10", "name": "10 食品與觀光", "desc": "食品安全、農業、飲食文化、觀光產業", "icon": "✈️"}
    ]
    return render_template('vocab_themes.html', student=student, themes=themes)
@app.route('/vocab/<int:student_id>/<theme_id>')
def vocab_area(student_id, theme_id):
    student = Student.query.get(student_id)
    if not student: return "找不到學生資料"

    # 用 like 語法找出開頭符合 theme_id 的主題 (例如找 "01" 會撈出 "01 教育與職涯")
    words_to_learn = Vocabulary.query.filter(
        Vocabulary.category == student.enrolled_course,
        Vocabulary.theme.like(f"{theme_id}%")
    ).all()

    words_data = [{"id": w.id, "theme": w.theme, "word": w.word, "meaning": w.meaning, "sentence": w.sentence} for w in words_to_learn]
    
    return render_template('ielts.html', words=words_data, student_id=student_id, theme_id=theme_id)
@app.route('/profile/<int:student_id>')
def student_profile(student_id):
    student = Student.query.get(student_id)
    all_vocab = Vocabulary.query.filter_by(category=student.enrolled_course).all()
    familiar_records = LearningProgress.query.filter_by(student_id=student_id, status='familiar').all()
    familiar_ids = [record.vocab_id for record in familiar_records]
    collection = []
    for index, v in enumerate(all_vocab, start=1):
        collection.append({ "number": index, "word": v.word, "meaning": v.meaning, "is_unlocked": v.id in familiar_ids })
    return render_template('profile.html', student=student, collection=collection, unlocked_count=len(familiar_ids), total_count=len(all_vocab))

@app.route('/api/update_progress', methods=['POST'])
def update_progress():
    data = request.json
    record = LearningProgress.query.filter_by(student_id=data.get('student_id'), vocab_id=data.get('vocab_id')).first()
    if record:
        record.status = data.get('status')
        record.last_reviewed = datetime.utcnow()
    else:
        new_record = LearningProgress(student_id=data.get('student_id'), vocab_id=data.get('vocab_id'), status=data.get('status'))
        db.session.add(new_record)
    db.session.commit()
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(debug=True)