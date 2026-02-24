from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """用户注册"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # 验证输入
        if not username or not email or not password:
            flash('请填写所有字段', 'danger')
            return render_template('register.html')

        if password != confirm_password:
            flash('两次密码输入不一致', 'danger')
            return render_template('register.html')

        if len(password) < 6:
            flash('密码长度至少6位', 'danger')
            return render_template('register.html')

        # 检查用户名是否已存在
        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'danger')
            return render_template('register.html')

        # 检查邮箱是否已存在
        if User.query.filter_by(email=email).first():
            flash('邮箱已被注册', 'danger')
            return render_template('register.html')

        # 创建新用户
        user = User(username=username, email=email)
        user.set_password(password)

        try:
            db.session.add(user)
            db.session.commit()
            flash('注册成功！请登录', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash('注册失败，请重试', 'danger')
            return render_template('register.html')

    return render_template('register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录"""
    if request.method == 'POST':
        username_or_email = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)

        if not username_or_email or not password:
            flash('请输入用户名/邮箱和密码', 'danger')
            return render_template('login.html')

        # 查找用户（支持用户名或邮箱登录）
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()

        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash(f'欢迎回来，{user.username}！', 'success')

            # 重定向到之前访问的页面或仪表盘
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('dashboard'))
        else:
            flash('用户名/邮箱或密码错误', 'danger')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """用户退出"""
    logout_user()
    flash('已成功退出', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """用户设置"""
    if request.method == 'POST':
        # 更新用户设置
        current_user.daily_start_hour = int(request.form.get('daily_start_hour', 8))
        current_user.daily_end_hour = int(request.form.get('daily_end_hour', 23))
        current_user.max_work_hours = int(request.form.get('max_work_hours', 10))

        try:
            db.session.commit()
            flash('设置已保存', 'success')
        except Exception as e:
            db.session.rollback()
            flash('保存失败，请重试', 'danger')

    return render_template('settings.html')
