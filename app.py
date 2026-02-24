import os
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, flash
from flask_login import LoginManager, current_user
from dotenv import load_dotenv
from models import db, User

# 加载环境变量
load_dotenv()

# 创建Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# 数据库配置：Render使用PostgreSQL，本地开发使用SQLite
if os.getenv('DATABASE_URL'):
    # Render提供的PostgreSQL数据库
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL').replace('postgres://', 'postgresql://')
else:
    # 本地开发使用SQLite
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///timemaster.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# DeepSeek API配置
app.config['DEEPSEEK_API_KEY'] = os.getenv('DEEPSEEK_API_KEY', '')
app.config['DEEPSEEK_BASE_URL'] = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')

# 初始化数据库
db.init_app(app)

# 初始化登录管理器
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录'
login_manager.login_message_category = 'warning'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# 注册蓝图
from routes.auth import auth_bp
from routes.tasks import tasks_bp
from routes.schedule import schedule_bp
from routes.summary import summary_bp
from routes.reward import reward_bp
from routes.habits import habits_bp
from routes.fixed import fixed_bp
from routes.progress import progress_bp
from routes.reflection import reflection_bp

app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(tasks_bp, url_prefix='/tasks')
app.register_blueprint(schedule_bp, url_prefix='/schedule')
app.register_blueprint(summary_bp, url_prefix='/summary')
app.register_blueprint(reward_bp, url_prefix='/reward')
app.register_blueprint(habits_bp, url_prefix='/habits')
app.register_blueprint(fixed_bp, url_prefix='/fixed')
app.register_blueprint(progress_bp, url_prefix='/progress')
app.register_blueprint(reflection_bp, url_prefix='/reflection')

# 注册自定义过滤器
from filters import register_filters
register_filters(app)

# 主页路由
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('auth.login'))

@app.route('/dashboard')
def dashboard():
    """主仪表盘"""
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))

    from models import Task, Schedule, Summary, Habit

    today = datetime.now().date()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())

    # 今日日程
    today_schedules = Schedule.query.filter(
        Schedule.user_id == current_user.id,
        Schedule.date == today
    ).order_by(Schedule.start_time).all()

    # 最近的未完成高优先任务
    urgent_tasks = Task.query.filter(
        Task.user_id == current_user.id,
        Task.status == 'pending',
        Task.priority == '高'
    ).order_by(Task.deadline).limit(5).all()

    # 今日完成进度
    completed_today = Schedule.query.filter(
        Schedule.user_id == current_user.id,
        Schedule.date == today,
        Schedule.status == 'completed'
    ).count()
    total_today = len(today_schedules)
    today_progress = int(completed_today / total_today * 100) if total_today > 0 else 0

    # 最新总结
    latest_summary = Summary.query.filter_by(
        user_id=current_user.id
    ).order_by(Summary.created_at.desc()).first()

    # 获取可兑换奖励
    from models import Reward
    rewards = Reward.query.filter_by(
        user_id=current_user.id,
        is_redeemed=False
    ).order_by(Reward.points_required.asc()).limit(5).all()

    # 获取用户积分
    user_points = current_user.total_points

    # 今日习惯打卡
    all_habits = Habit.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).all()

    today_habits = []
    for habit in all_habits:
        if habit.should_do_today():
            checkin = habit.get_today_checkin()
            today_habits.append({
                'habit': habit,
                'checked': checkin is not None,
                'streak': habit.get_current_streak()
            })

    return render_template('dashboard.html',
                         today_schedules=today_schedules,
                         urgent_tasks=urgent_tasks,
                         today_progress=today_progress,
                         completed_today=completed_today,
                         total_today=total_today,
                         latest_summary=latest_summary,
                         rewards=rewards,
                         user_points=user_points,
                         today=today,
                         today_habits=today_habits)

# 上下文处理器 - 注入当前时间和问候语
@app.context_processor
def inject_now():
    from flask import request
    now = datetime.now()
    hour = now.hour

    # 动态问候
    if hour < 6:
        greeting = '夜深了'
        daily_encouragement = '注意休息，身体最重要 💤'
        daily_emoji = '🌙'
    elif hour < 9:
        greeting = '早上好'
        daily_encouragement = '美好的一天开始了，加油！☀️'
        daily_emoji = '🌅'
    elif hour < 12:
        greeting = '上午好'
        daily_encouragement = '保持专注，你可以的！💪'
        daily_emoji = '📚'
    elif hour < 14:
        greeting = '中午好'
        daily_encouragement = '记得休息和吃饭哦~ 🍜'
        daily_emoji = '☕'
    elif hour < 18:
        greeting = '下午好'
        daily_encouragement = '继续加油，你很棒！🌟'
        daily_emoji = '💫'
    elif hour < 22:
        greeting = '晚上好'
        daily_encouragement = '今天辛苦了，好好放松~ 🌙'
        daily_emoji = '🛋️'
    else:
        greeting = '夜深了'
        daily_encouragement = '早点休息，明天见 😴'
        daily_emoji = '🌜'

    # 每日激励语录
    quotes = [
        "种一棵树最好的时间是十年前，其次是现在。💪",
        "每一个不曾起舞的日子，都是对生命的辜负。✨",
        "你今天的努力，是幸运的伏笔。🍀",
        "星光不问赶路人，时光不负有心人。⭐",
        "不积跬步，无以至千里。👣",
        "坚持下去，你想要的都会有。🎯",
        "每天进步一点点，成功离你更近一点。📈",
        "相信自己的力量，你可以做到的！💫"
    ]
    import random
    motivational_quote = random.choice(quotes)

    return {
        'now': now,
        'greeting_message': greeting,
        'daily_encouragement': daily_encouragement,
        'daily_emoji': daily_emoji,
        'motivational_quote': motivational_quote
    }

# 创建数据库表并执行迁移
with app.app_context():
    db.create_all()

    # 自动迁移：添加 total_hours 字段到 category_progress 表
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('category_progress')]

        if 'total_hours' not in columns:
            print("检测到 category_progress 表缺少 total_hours 字段，正在添加...")
            if 'postgresql' in str(db.engine.url):
                db.session.execute(text("ALTER TABLE category_progress ADD COLUMN total_hours FLOAT DEFAULT 0.0"))
            else:  # SQLite
                db.session.execute(text("ALTER TABLE category_progress ADD COLUMN total_hours FLOAT DEFAULT 0.0"))
            db.session.commit()
            print("✓ total_hours 字段添加成功！")
    except Exception as e:
        print(f"迁移检查: {e}")
        db.session.rollback()

if __name__ == '__main__':
    # 生产环境不使用debug模式
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
