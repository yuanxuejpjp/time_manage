from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """用户模型"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # 积分系统
    total_points = db.Column(db.Integer, default=0)  # 累计积分
    # 用户设置
    daily_start_hour = db.Column(db.Integer, default=10)  # 每日开始时间（默认10点）
    daily_end_hour = db.Column(db.Integer, default=17)    # 每日结束时间（默认17点）
    max_work_hours = db.Column(db.Integer, default=7)     # 每日最大工作时长（7小时）

    # 关系
    tasks = db.relationship('Task', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    schedules = db.relationship('Schedule', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    feedbacks = db.relationship('Feedback', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    summaries = db.relationship('Summary', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    rewards = db.relationship('Reward', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    category_progress = db.relationship('RewardProgress', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    habits = db.relationship('Habit', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    habit_checkins = db.relationship('HabitCheckin', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    fixed_schedules = db.relationship('FixedSchedule', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    important_dates = db.relationship('ImportantDate', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    points_history = db.relationship('PointsHistory', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        """设置密码哈希"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """验证密码"""
        return check_password_hash(self.password_hash, password)


class Task(db.Model):
    """任务模型"""
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # 基本信息
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    estimated_hours = db.Column(db.Float, default=1.0)  # 预计耗时（小时）
    deadline = db.Column(db.DateTime)  # 截止日期时间
    priority = db.Column(db.String(10), default='中')  # 高/中/低
    category = db.Column(db.String(50), default='其他')  # 分类
    is_meeting = db.Column(db.Boolean, default=False)  # 是否为会议（紧急事项）
    location = db.Column(db.String(200))  # 会议地点

    # 重复设置
    is_recurring = db.Column(db.Boolean, default=False)  # 是否重复
    recurring_type = db.Column(db.String(20))  # 'daily', 'weekly', 'weekly_days'
    recurring_days = db.Column(db.String(20))  # 如 "1,3,5" 表示周一、三、五（0=周一，6=周日）
    recurring_end_date = db.Column(db.DateTime)  # 重复结束日期

    # 状态
    status = db.Column(db.String(20), default='pending')  # pending, completed, cancelled
    completed_at = db.Column(db.DateTime)

    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        """转换为字典，用于发送给AI"""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'estimated_hours': self.estimated_hours,
            'deadline': self.deadline.isoformat() if self.deadline else None,
            'priority': self.priority,
            'category': self.category,
            'status': self.status,
            'is_meeting': self.is_meeting,
            'location': self.location
        }


class Schedule(db.Model):
    """日程安排模型"""
    __tablename__ = 'schedules'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # 日程信息
    date = db.Column(db.Date, nullable=False, index=True)  # 日程日期
    start_time = db.Column(db.Time, nullable=False)  # 开始时间
    end_time = db.Column(db.Time, nullable=False)    # 结束时间
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))  # 关联任务
    task_title = db.Column(db.String(200))  # 任务标题（冗余，方便查询）
    category = db.Column(db.String(50))  # 分类
    is_break = db.Column(db.Boolean, default=False)  # 是否为休息时间
    is_meeting = db.Column(db.Boolean, default=False)  # 是否为会议（紧急事项）
    location = db.Column(db.String(200))  # 地点

    # AI生成信息
    generated_by_ai = db.Column(db.Boolean, default=True)
    ai_reasoning = db.Column(db.Text)  # AI安排理由

    # 状态
    status = db.Column(db.String(20), default='scheduled')  # scheduled, completed, partial, cancelled

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 关系
    task = db.relationship('Task', backref='schedules')
    feedback = db.relationship('Feedback', backref='schedule', uselist=False, cascade='all, delete-orphan')


class Feedback(db.Model):
    """每日反馈模型"""
    __tablename__ = 'feedbacks'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedules.id'), nullable=False)

    # 反馈信息
    completion_status = db.Column(db.String(20), default='未开始')  # 已完成/部分完成/未开始/取消
    actual_hours = db.Column(db.Float)  # 实际花费时间
    notes = db.Column(db.Text)  # 备注

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Summary(db.Model):
    """总结报表模型"""
    __tablename__ = 'summaries'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # 总结类型
    summary_type = db.Column(db.String(10), nullable=False)  # daily, weekly, monthly
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

    # 统计数据
    total_tasks = db.Column(db.Integer, default=0)
    completed_tasks = db.Column(db.Integer, default=0)
    completion_rate = db.Column(db.Float, default=0.0)
    total_hours = db.Column(db.Float, default=0.0)

    # 分类统计（JSON存储）
    category_stats = db.Column(db.Text)  # JSON: {"上课": 10.5, "科研": 15.0}

    # AI生成内容
    ai_summary = db.Column(db.Text)  # AI生成的总结
    ai_suggestions = db.Column(db.Text)  # AI建议

    # 用户心得
    user_notes = db.Column(db.Text)  # 用户的留言/心得

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_category_stats(self):
        """获取分类统计数据"""
        import json
        if self.category_stats:
            return json.loads(self.category_stats)
        return {}

    def set_category_stats(self, stats_dict):
        """设置分类统计数据"""
        import json
        self.category_stats = json.dumps(stats_dict, ensure_ascii=False)


class Reward(db.Model):
    """奖励规则模型"""
    __tablename__ = 'rewards'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # 奖励信息
    title = db.Column(db.String(200), nullable=False)  # 奖励名称
    description = db.Column(db.Text)  # 描述
    points_required = db.Column(db.Integer, default=100)  # 所需积分
    icon = db.Column(db.String(50), default='gift')  # 图标

    # 状态
    is_redeemed = db.Column(db.Boolean, default=False)  # 是否已兑换
    redeemed_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class RewardProgress(db.Model):
    """分类积分进度模型"""
    __tablename__ = 'category_progress'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # 进度信息
    category = db.Column(db.String(50), nullable=False, index=True)  # 分类
    total_points = db.Column(db.Integer, default=0)  # 该分类累计积分
    checkin_count = db.Column(db.Integer, default=0)  # 打卡次数
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<CategoryProgress {self.category}: {self.total_points}pts>'


class PointsHistory(db.Model):
    """积分历史记录模型"""
    __tablename__ = 'points_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # 交易信息
    points_change = db.Column(db.Integer, nullable=False)  # 积分变化（正数为获得，负数为消费）
    source_type = db.Column(db.String(20), nullable=False)  # 来源类型: habit_checkin, reward_redeem
    source_id = db.Column(db.Integer)  # 来源ID（习惯ID或奖励ID）
    description = db.Column(db.String(200))  # 描述

    # 余额快照
    balance_after = db.Column(db.Integer, nullable=False)  # 交易后余额

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<PointsHistory {self.points_change:+d}: {self.description}>'


class Habit(db.Model):
    """习惯模型"""
    __tablename__ = 'habits'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # 基本信息
    title = db.Column(db.String(200), nullable=False)  # 习惯名称
    description = db.Column(db.Text)  # 描述
    category = db.Column(db.String(50), default='其他')  # 分类
    icon = db.Column(db.String(50), default='star')  # 图标（用于显示）

    # 频率设置
    frequency = db.Column(db.String(20), default='daily')  # daily, weekly, weekdays, weekends
    target_days = db.Column(db.String(20))  # 如 "0,1,2,3,4,5,6" 表示每周几（0=周一，6=周日）

    # 目标设定
    target_value = db.Column(db.Float, default=1.0)  # 目标值（如30分钟、10页）
    target_unit = db.Column(db.String(20), default='次')  # 单位（次、分钟、页、小时等）

    # 积分奖励
    points_value = db.Column(db.Integer, default=10)  # 每次打卡获得的积分

    # 提醒时间
    reminder_time = db.Column(db.Time)  # 每日提醒时间

    # 状态
    is_active = db.Column(db.Boolean, default=True)
    streak_days = db.Column(db.Integer, default=0)  # 连续打卡天数
    total_checkins = db.Column(db.Integer, default=0)  # 累计打卡次数

    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    checkins = db.relationship('HabitCheckin', backref='habit', lazy='dynamic', cascade='all, delete-orphan')

    def should_do_today(self):
        """判断今天是否应该执行此习惯"""
        today = datetime.now().date()
        weekday = today.weekday()  # 0=周一, 6=周日

        if self.frequency == 'daily':
            return True
        elif self.frequency == 'weekdays':
            return weekday < 5  # 周一到周五
        elif self.frequency == 'weekends':
            return weekday >= 5  # 周六、周日
        elif self.frequency == 'weekly' and self.target_days:
            days = [int(d) for d in self.target_days.split(',')]
            return weekday in days

        return False

    def get_today_checkin(self):
        """获取今天的打卡记录"""
        today = datetime.now().date()
        return self.checkins.filter_by(checkin_date=today).first()

    def get_current_streak(self):
        """获取当前连续打卡天数"""
        streak = 0
        checkin_date = datetime.now().date()

        while True:
            record = self.checkins.filter_by(checkin_date=checkin_date).first()
            if record:
                streak += 1
                checkin_date -= timedelta(days=1)
            else:
                break

        return streak


class FixedSchedule(db.Model):
    """固定日程模型 - 每周固定时间的活动"""
    __tablename__ = 'fixed_schedules'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # 基本信息
    title = db.Column(db.String(200), nullable=False)  # 活动名称
    description = db.Column(db.Text)  # 描述
    category = db.Column(db.String(50), default='其他')  # 分类
    location = db.Column(db.String(200))  # 地点

    # 时间设置
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=周一, 6=周日
    start_time = db.Column(db.Time, nullable=False)  # 开始时间
    end_time = db.Column(db.Time, nullable=False)  # 结束时间

    # 时间范围
    start_date = db.Column(db.Date, nullable=False)  # 开始日期
    end_date = db.Column(db.Date)  # 结束日期（可选，如8周后）

    # 提醒
    reminder_minutes = db.Column(db.Integer, default=30)  # 提前多少分钟提醒

    # 状态
    is_active = db.Column(db.Boolean, default=True)
    color = db.Column(db.String(20), default='primary')  # 显示颜色

    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<FixedSchedule {self.title} {self.start_time}-{self.end_time}>'


class ImportantDate(db.Model):
    """重要日子模型 - 生日、纪念日、截止日期等"""
    __tablename__ = 'important_dates'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # 基本信息
    title = db.Column(db.String(200), nullable=False)  # 标题
    description = db.Column(db.Text)  # 描述
    date_type = db.Column(db.String(20), default='other')  # birthday, anniversary, deadline, holiday, other
    event_date = db.Column(db.Date, nullable=False, index=True)  # 日期
    event_time = db.Column(db.Time)  # 具体时间（可选）

    # 重复设置
    is_recurring = db.Column(db.Boolean, default=False)  # 是否每年重复
    recurring_month = db.Column(db.Integer)  # 如果重复，月份（1-12）
    recurring_day = db.Column(db.Integer)  # 如果重复，日期

    # 提醒
    remind_days_before = db.Column(db.Integer, default=0)  # 提前几天提醒（0=当天）
    is_reminded = db.Column(db.Boolean, default=False)  # 是否已提醒

    # 状态
    is_completed = db.Column(db.Boolean, default=False)  # 是否已完成/已过

    # 颜色标记
    color = db.Column(db.String(20), default='info')  # 显示颜色

    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<ImportantDate {self.title} {self.event_date}>'


class HabitCheckin(db.Model):
    """习惯打卡记录模型"""
    __tablename__ = 'habit_checkins'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    habit_id = db.Column(db.Integer, db.ForeignKey('habits.id'), nullable=False)

    # 打卡信息
    checkin_date = db.Column(db.Date, nullable=False, index=True)  # 打卡日期
    actual_value = db.Column(db.Float, default=1.0)  # 实际完成值
    notes = db.Column(db.Text)  # 备注

    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<HabitCheckin {self.checkin_date}: {self.actual_value}>'


class DailyReflection(db.Model):
    """每日复盘模型"""
    __tablename__ = 'daily_reflections'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reflection_date = db.Column(db.Date, nullable=False, index=True)  # 复盘日期

    # 【1. 今日核心推进】
    core_progress = db.Column(db.Text)  # 今日核心推进内容
    is_long_term_value = db.Column(db.Boolean)  # 是否产生长期价值

    # 【2. 深度工作】
    deep_work_hours = db.Column(db.Float)  # 深度工作时间（小时）
    high_energy_period = db.Column(db.String(50))  # 高能区间描述

    # 【3. 核心领悟】
    key_insight = db.Column(db.Text)  # 今日关键认知
    changed_judgment = db.Column(db.Boolean)  # 是否改变原有判断
    influences_future = db.Column(db.Boolean)  # 未来是否影响决策

    # 【4. 偏差分析】
    time_waste = db.Column(db.Text)  # 今日最大时间浪费
    waste_reason = db.Column(db.Text)  # 原因

    # 【5. 明日唯一关键任务（MIT）】
    tomorrow_mit = db.Column(db.Text)  # 明日唯一关键任务

    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 唯一约束：每个用户每天只能有一条复盘
    __table_args__ = (
        db.UniqueConstraint('user_id', 'reflection_date', name='unique_daily_reflection'),
    )

    def __repr__(self):
        return f'<DailyReflection {self.reflection_date}: MIT={self.tomorrow_mit}>'
