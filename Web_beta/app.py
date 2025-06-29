from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import os
import sys
import logging
from dotenv import load_dotenv
from models import db, User, Post, Comment, Like, Complaint, Todo

# 设置日志记录
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# 加载环境变量
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key')

# 配置数据库
database_url = os.getenv('DATABASE_URL')
if database_url:
    # 修复 Render 的 PostgreSQL URL
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    logging.info(f"Database URL configured: {database_url.split('@')[0]}@*****")
else:
    logging.error("No DATABASE_URL environment variable found!")
    
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化数据库
db.init_app(app)

@app.errorhandler(500)
def internal_error(error):
    logging.error(f"Internal Server Error: {error}")
    return "Internal Server Error", 500

@app.errorhandler(404)
def not_found_error(error):
    logging.error(f"Page Not Found: {error}")
    return "Page Not Found", 404

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'username' in session:
        username = session['username']
        user = User.query.filter_by(username=username).first()
        if user is None:
            session.clear()  # 清除无效的session
            return redirect(url_for('login'))
        is_admin = user.login_type == 'admin'
        return render_template('dashboard.html', 
                            username=username,
                            is_admin=is_admin)
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    message = ''
    if request.method == 'POST':
        login_type = request.args.get('type', 'birth')
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if login_type == 'admin':
            if user and user.login_type == 'admin':
                if check_password_hash(user.password, password):
                    session['username'] = username
                    return redirect(url_for('index'))
                else:
                    message = '用户名或密码错误。'
            else:
                message = '用户名或密码错误。'
        
        elif login_type == 'birth':
            birthdate = request.form['birthdate']
            if user and user.login_type == 'birth':
                if check_password_hash(user.password, password) and user.birthdate == birthdate:
                    session['username'] = username
                    return redirect(url_for('index'))
                else:
                    message = '用户名、密码或出生日期不正确。'
            else:
                message = '此用户名未被预设，请联系管理员。'
    
    return render_template('login.html', message=message)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/todos')
@login_required
def todos():
    username = session['username']
    user = User.query.filter_by(username=username).first()
    todos = Todo.query.filter_by(user_id=user.id).order_by(
        Todo.completed,
        Todo.priority != 'urgent',
        Todo.priority != 'medium',
        Todo.created_at.desc()
    ).all()
    
    return render_template('todos.html', 
                        todos=todos,
                        username=username)

@app.route('/add-todo', methods=['POST'])
@login_required
def add_todo():
    username = session['username']
    user = User.query.filter_by(username=username).first()
    task = request.form.get('task')
    date = request.form.get('date', '')
    time = request.form.get('time', '')
    priority = request.form.get('priority', 'medium')
    
    if task:
        new_todo = Todo(
            task=task,
            date=date,
            time=time,
            priority=priority,
            user_id=user.id
        )
        db.session.add(new_todo)
        db.session.commit()
    
    return redirect(url_for('todos'))

@app.route('/toggle-todo/<int:todo_id>')
@login_required
def toggle_todo(todo_id):
    username = session['username']
    user = User.query.filter_by(username=username).first()
    todo = Todo.query.filter_by(id=todo_id, user_id=user.id).first()
    
    if todo:
        todo.completed = not todo.completed
        db.session.commit()
    
    return redirect(url_for('todos'))

@app.route('/delete-todo/<int:todo_id>')
@login_required
def delete_todo(todo_id):
    username = session['username']
    user = User.query.filter_by(username=username).first()
    todo = Todo.query.filter_by(id=todo_id, user_id=user.id).first()
    
    if todo:
        db.session.delete(todo)
        db.session.commit()
    
    return redirect(url_for('todos'))

@app.route('/user-management')
@login_required
def user_management():
    username = session['username']
    user = User.query.filter_by(username=username).first()
    
    if user.login_type != 'admin':
        return redirect(url_for('index'))
    
    users = User.query.filter_by(login_type='birth').all()
    users_dict = {user.username: {'birthdate': user.birthdate} for user in users}
    return render_template('user_management.html', users=users_dict)

@app.route('/create-user', methods=['POST'])
@login_required
def create_user():
    admin_username = session['username']
    admin = User.query.filter_by(username=admin_username).first()
    
    if admin.login_type != 'admin':
        return redirect(url_for('index'))
    
    username = request.form.get('username')
    password = request.form.get('password')
    birthdate = request.form.get('birthdate')
    
    if username and password and birthdate:
        if User.query.filter_by(username=username).first():
            users = User.query.filter_by(login_type='birth').all()
            return render_template('user_management.html', 
                                message='用户名已存在',
                                success=False,
                                users=users)
        
        new_user = User(
            username=username,
            password=generate_password_hash(password),
            birthdate=birthdate,
            login_type='birth',
            created_by=admin_username
        )
        db.session.add(new_user)
        db.session.commit()
        
        users = User.query.filter_by(login_type='birth').all()
        return render_template('user_management.html', 
                            message='用户创建成功',
                            success=True,
                            users=users)
    
    users = User.query.filter_by(login_type='birth').all()
    return render_template('user_management.html', 
                        message='请填写所有必填字段',
                        success=False,
                        users=users)

@app.route('/delete-user/<username>')
@login_required
def delete_user(username):
    admin_username = session['username']
    admin = User.query.filter_by(username=admin_username).first()
    
    if admin.login_type != 'admin':
        return redirect(url_for('index'))
    
    user = User.query.filter_by(username=username).first()
    if user and user.username != admin_username:
        # 删除用户的所有数据
        Todo.query.filter_by(user_id=user.id).delete()
        Like.query.filter_by(user_id=user.id).delete()
        Complaint.query.filter_by(user_id=user.id).delete()
        Comment.query.filter_by(author_id=user.id).delete()
        Post.query.filter_by(author_id=user.id).delete()
        db.session.delete(user)
        db.session.commit()
    
    return redirect(url_for('user_management'))

@app.route('/view-user-todos/<username>')
@login_required
def view_user_todos(username):
    admin_username = session['username']
    admin = User.query.filter_by(username=admin_username).first()
    
    if admin.login_type != 'admin':
        return redirect(url_for('index'))
    
    user = User.query.filter_by(username=username).first()
    if not user:
        return redirect(url_for('user_management'))
    
    todos = Todo.query.filter_by(user_id=user.id).order_by(
        Todo.completed,
        Todo.priority != 'urgent',
        Todo.priority != 'medium',
        Todo.created_at.desc()
    ).all()
    
    return render_template('user_todos.html', 
                        todos=todos,
                        target_username=username,
                        user_data={'username': username})

@app.route('/forum')
@login_required
def forum():
    username = session['username']
    user = User.query.filter_by(username=username).first()
    is_admin = user.login_type == 'admin'
    
    posts = Post.query.order_by(Post.created_at.desc()).all()
    
    # 处理每个帖子的数据
    for post in posts:
        post.like_count = post.likes.count()
        post.complaint_count = post.complaints.count()
        post.is_liked = post.likes.filter_by(user_id=user.id).first() is not None
        post.is_complained = post.complaints.filter_by(user_id=user.id).first() is not None
        post.author_name = post.author.username
        
        # 处理评论数据
        comments = Comment.query.filter_by(post_id=post.id).all()
        for comment in comments:
            comment.author_name = comment.author.username
        post.comments = comments
    
    return render_template('forum.html', 
                        username=username,
                        is_admin=is_admin,
                        posts=posts)

@app.route('/create-post', methods=['POST'])
@login_required
def create_post():
    username = session['username']
    user = User.query.filter_by(username=username).first()
    content = request.form.get('content')
    
    if content:
        new_post = Post(
            content=content,
            author_id=user.id
        )
        db.session.add(new_post)
        db.session.commit()
    
    return redirect(url_for('forum'))

@app.route('/create-comment/<int:post_id>', methods=['POST'])
@login_required
def create_comment(post_id):
    username = session['username']
    user = User.query.filter_by(username=username).first()
    content = request.form.get('content')
    
    if content:
        new_comment = Comment(
            content=content,
            post_id=post_id,
            author_id=user.id
        )
        db.session.add(new_comment)
        db.session.commit()
    
    return redirect(url_for('forum'))

@app.route('/toggle-like/<int:post_id>')
@login_required
def toggle_like(post_id):
    username = session['username']
    user = User.query.filter_by(username=username).first()
    
    like = Like.query.filter_by(post_id=post_id, user_id=user.id).first()
    if like:
        db.session.delete(like)
    else:
        new_like = Like(post_id=post_id, user_id=user.id)
        db.session.add(new_like)
    
    db.session.commit()
    return redirect(url_for('forum'))

@app.route('/toggle-complaint/<int:post_id>')
@login_required
def toggle_complaint(post_id):
    username = session['username']
    user = User.query.filter_by(username=username).first()
    
    complaint = Complaint.query.filter_by(post_id=post_id, user_id=user.id).first()
    if complaint:
        db.session.delete(complaint)
    else:
        new_complaint = Complaint(post_id=post_id, user_id=user.id)
        db.session.add(new_complaint)
    
    db.session.commit()
    return redirect(url_for('forum'))

@app.route('/delete-post/<int:post_id>')
@login_required
def delete_post(post_id):
    username = session['username']
    user = User.query.filter_by(username=username).first()
    
    if user.login_type != 'admin':
        return redirect(url_for('forum'))
    
    post = Post.query.get(post_id)
    if post:
        # 删除相关的评论、点赞和投诉
        Comment.query.filter_by(post_id=post_id).delete()
        Like.query.filter_by(post_id=post_id).delete()
        Complaint.query.filter_by(post_id=post_id).delete()
        db.session.delete(post)
        db.session.commit()
    
    return redirect(url_for('forum'))

@app.route('/group-leader')
@login_required
def group_leader():
    username = session['username']
    users = User.query.all()
    
    # 计算每个用户的统计数据
    for user in users:
        # 获取用户的所有帖子
        posts = Post.query.filter_by(author_id=user.id).all()
        
        # 计算总点赞和投诉数
        total_likes = sum(post.likes.count() for post in posts)
        total_complaints = sum(post.complaints.count() for post in posts)
        
        # 添加到用户对象
        user.total_likes = total_likes
        user.total_complaints = total_complaints
        user.net_score = total_likes - total_complaints
    
    # 按净得分降序排序
    users.sort(key=lambda x: (-x.net_score, x.username))
    
    return render_template('group_leader.html', users=users)

# API 端点
@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': '无效的请求数据'
            }), 400

        username = data.get('username')
        password = data.get('password')
        is_admin = data.get('is_admin', False)
        birth_date = data.get('birth_date')

        if not username or not password:
            return jsonify({
                'success': False,
                'message': '用户名和密码不能为空'
            }), 400

        user = User.query.filter_by(username=username).first()

        if not user:
            return jsonify({
                'success': False,
                'message': '用户不存在'
            }), 401

        if is_admin and user.login_type != 'admin':
            return jsonify({
                'success': False,
                'message': '无管理员权限'
            }), 401

        if not is_admin and user.login_type != 'birth':
            return jsonify({
                'success': False,
                'message': '无效的用户类型'
            }), 401

        if not check_password_hash(user.password, password):
            return jsonify({
                'success': False,
                'message': '密码错误'
            }), 401

        if not is_admin and user.birthdate != birth_date:
            return jsonify({
                'success': False,
                'message': '出生日期错误'
            }), 401

        # 生成 token（这里简单使用用户名作为 token，实际应使用 JWT）
        token = username

        return jsonify({
            'success': True,
            'message': '登录成功',
            'token': token,
            'user': {
                'id': user.id,
                'username': user.username,
                'birthDate': user.birthdate,
                'isAdmin': user.login_type == 'admin'
            }
        }), 200

    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return jsonify({
            'success': False,
            'message': '服务器错误'
        }), 500

@app.route('/api/todos', methods=['GET'])
def api_get_todos():
    # 这里应该添加 token 验证
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': '需要用户ID'}), 400
        
    todos = Todo.query.filter_by(user_id=user_id).order_by(
        Todo.completed,
        Todo.priority != 'urgent',
        Todo.priority != 'medium',
        Todo.created_at.desc()
    ).all()
    
    return jsonify({
        'todos': [{
            'id': todo.id,
            'task': todo.task,
            'date': todo.date,
            'time': todo.time,
            'priority': todo.priority,
            'completed': todo.completed,
            'created_at': todo.created_at.isoformat()
        } for todo in todos]
    })

@app.route('/api/todos', methods=['POST'])
def api_create_todo():
    # 这里应该添加 token 验证
    data = request.get_json()
    user_id = data.get('user_id')
    task = data.get('task')
    date = data.get('date', '')
    time = data.get('time', '')
    priority = data.get('priority', 'medium')
    
    if not all([user_id, task]):
        return jsonify({'error': '缺少必要参数'}), 400
    
    new_todo = Todo(
        task=task,
        date=date,
        time=time,
        priority=priority,
        user_id=user_id
    )
    db.session.add(new_todo)
    db.session.commit()
    
    return jsonify({
        'id': new_todo.id,
        'task': new_todo.task,
        'date': new_todo.date,
        'time': new_todo.time,
        'priority': new_todo.priority,
        'completed': new_todo.completed,
        'created_at': new_todo.created_at.isoformat()
    }), 201

# 创建数据库表
def init_db():
    try:
        with app.app_context():
            logging.info("Creating database tables...")
            db.create_all()
            
            # 检查是否需要创建管理员账户
            admin = User.query.filter_by(username='S1f').first()
            if not admin:
                logging.info("Creating admin user...")
                admin = User(
                    username='S1f',
                    password=generate_password_hash('yifan0316'),
                    login_type='admin'
                )
                db.session.add(admin)
                db.session.commit()
                logging.info("Admin user created successfully")
            else:
                logging.info("Admin user already exists")
    except Exception as e:
        logging.error(f"Error initializing database: {str(e)}")
        raise

if __name__ == '__main__':
    init_db()  # 初始化数据库
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
