from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from calendar import monthrange, month_name
from models import db, Habit, HabitCheckin

habits_bp = Blueprint('habits', __name__)


@habits_bp.route('/')
@login_required
def list_habits():
    """习惯列表"""
    # 获取所有激活的习惯
    habits = Habit.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).order_by(Habit.created_at.desc()).all()

    # 获取今天的打卡状态
    today_habits = []
    for habit in habits:
        if habit.should_do_today():
            checkin = habit.get_today_checkin()
            today_habits.append({
                'habit': habit,
                'checked': checkin is not None,
                'checkin': checkin
            })

    return render_template('habits.html', habits=habits, today_habits=today_habits)


@habits_bp.route('/add', methods=['POST'])
@login_required
def add_habit():
    """添加新习惯"""
    habit = Habit(user_id=current_user.id)

    # 基本信息
    habit.title = request.form.get('title', '').strip()
    habit.description = request.form.get('description', '').strip()
    habit.category = request.form.get('category', '其他').strip() or '其他'
    habit.icon = request.form.get('icon', 'star').strip() or 'star'

    # 频率设置
    habit.frequency = request.form.get('frequency', 'daily')
    if habit.frequency == 'weekly':
        days = request.form.getlist('target_days')
        habit.target_days = ','.join(days) if days else '0,1,2,3,4,5,6'

    # 目标设定
    habit.target_value = float(request.form.get('target_value', 1.0))
    habit.target_unit = request.form.get('target_unit', '次').strip() or '次'

    # 提醒时间
    reminder_time = request.form.get('reminder_time', '')
    if reminder_time:
        try:
            habit.reminder_time = datetime.strptime(reminder_time, '%H:%M').time()
        except:
            habit.reminder_time = None

    try:
        db.session.add(habit)
        db.session.commit()
        flash('习惯创建成功', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'创建失败：{str(e)}', 'danger')

    return redirect(url_for('habits.list_habits'))


@habits_bp.route('/<int:habit_id>/checkin', methods=['GET', 'POST'])
@login_required
def checkin(habit_id):
    """打卡"""
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        # 查找或创建今天的打卡记录
        today = date.today()
        checkin = HabitCheckin.query.filter_by(
            habit_id=habit_id,
            checkin_date=today
        ).first()

        if not checkin:
            checkin = HabitCheckin(
                user_id=current_user.id,
                habit_id=habit_id,
                checkin_date=today
            )
            db.session.add(checkin)

        # 更新打卡信息
        checkin.actual_value = float(request.form.get('actual_value', habit.target_value))
        checkin.notes = request.form.get('notes', '').strip()

        # 更新习惯统计
        habit.total_checkins += 1
        habit.streak_days = habit.get_current_streak()

        try:
            db.session.commit()
            flash(f'打卡成功！已连续坚持 {habit.streak_days} 天', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'打卡失败：{str(e)}', 'danger')

        return redirect(url_for('habits.list_habits'))

    return render_template('habit_checkin.html', habit=habit)


@habits_bp.route('/<int:habit_id>/undo', methods=['POST'])
@login_required
def undo_checkin(habit_id):
    """取消今天的打卡"""
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()

    today = date.today()
    checkin = HabitCheckin.query.filter_by(
        habit_id=habit_id,
        checkin_date=today
    ).first()

    if checkin:
        try:
            db.session.delete(checkin)
            habit.total_checkins -= 1
            habit.streak_days = habit.get_current_streak()
            db.session.commit()
            flash('已取消今天的打卡', 'info')
        except Exception as e:
            db.session.rollback()
            flash(f'操作失败：{str(e)}', 'danger')

    return redirect(url_for('habits.list_habits'))


@habits_bp.route('/<int:habit_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_habit(habit_id):
    """编辑习惯"""
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        # 基本信息
        habit.title = request.form.get('title', '').strip()
        habit.description = request.form.get('description', '').strip()
        habit.category = request.form.get('category', '其他').strip() or '其他'
        habit.icon = request.form.get('icon', 'star').strip() or 'star'

        # 频率设置
        habit.frequency = request.form.get('frequency', 'daily')
        if habit.frequency == 'weekly':
            days = request.form.getlist('target_days')
            habit.target_days = ','.join(days) if days else '0,1,2,3,4,5,6'
        else:
            habit.target_days = None

        # 目标设定
        habit.target_value = float(request.form.get('target_value', 1.0))
        habit.target_unit = request.form.get('target_unit', '次').strip() or '次'

        # 提醒时间
        reminder_time = request.form.get('reminder_time', '')
        if reminder_time:
            try:
                habit.reminder_time = datetime.strptime(reminder_time, '%H:%M').time()
            except:
                habit.reminder_time = None
        else:
            habit.reminder_time = None

        try:
            db.session.commit()
            flash('习惯更新成功', 'success')
            return redirect(url_for('habits.list_habits'))
        except Exception as e:
            db.session.rollback()
            flash(f'更新失败：{str(e)}', 'danger')

    return render_template('habit_form.html', habit=habit)


@habits_bp.route('/<int:habit_id>/toggle', methods=['POST'])
@login_required
def toggle_habit(habit_id):
    """启用/禁用习惯"""
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()

    habit.is_active = not habit.is_active

    try:
        db.session.commit()
        status = '启用' if habit.is_active else '禁用'
        flash(f'习惯已{status}', 'success')
    except Exception as e:
        db.session.rollback()
        flash('操作失败', 'danger')

    return redirect(url_for('habits.list_habits'))


@habits_bp.route('/<int:habit_id>/delete', methods=['POST'])
@login_required
def delete_habit(habit_id):
    """删除习惯"""
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()

    try:
        db.session.delete(habit)
        db.session.commit()
        flash('习惯已删除', 'success')
    except Exception as e:
        db.session.rollback()
        flash('删除失败', 'danger')

    return redirect(url_for('habits.list_habits'))


@habits_bp.route('/calendar')
@login_required
def calendar_view():
    """日历视图"""
    # 获取年份和月份参数
    year = int(request.args.get('year', datetime.now().year))
    month = int(request.args.get('month', datetime.now().month))

    # 获取当月第一天和最后一天
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])

    # 获取所有激活的习惯
    habits = Habit.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).all()

    # 获取当月的所有打卡记录
    checkins = HabitCheckin.query.filter(
        HabitCheckin.user_id == current_user.id,
        HabitCheckin.checkin_date >= first_day,
        HabitCheckin.checkin_date <= last_day
    ).all()

    # 构建打卡数据字典
    checkin_dict = {}
    for checkin in checkins:
        day = checkin.checkin_date.day
        if day not in checkin_dict:
            checkin_dict[day] = []
        checkin_dict[day].append(checkin.habit_id)

    # 计算上个月和下个月
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    return render_template('habit_calendar.html',
                         year=year,
                         month=month,
                         month_name=month_name[month],
                         habits=habits,
                         checkin_dict=checkin_dict,
                         first_day=first_day,
                         last_day=last_day,
                         prev_year=prev_year,
                         prev_month=prev_month,
                         next_year=next_year,
                         next_month=next_month)


@habits_bp.route('/stats')
@login_required
def stats():
    """统计分析"""
    habits = Habit.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).all()

    # 为每个习惯计算统计数据
    habit_stats = []
    for habit in habits:
        # 获取最近30天的打卡记录
        thirty_days_ago = date.today() - timedelta(days=30)
        recent_checkins = habit.checkins.filter(
            HabitCheckin.checkin_date >= thirty_days_ago
        ).all()

        # 计算完成率
        should_do_days = 0
        completed_days = 0

        for i in range(30):
            check_date = thirty_days_ago + timedelta(days=i)
            # 简单判断：如果是每日习惯，每天都应该做
            if habit.frequency == 'daily':
                should_do_days += 1
                if habit.checkins.filter_by(checkin_date=check_date).first():
                    completed_days += 1

        completion_rate = int(completed_days / should_do_days * 100) if should_do_days > 0 else 0

        habit_stats.append({
            'habit': habit,
            'total_checkins': habit.total_checkins,
            'current_streak': habit.get_current_streak(),
            'completion_rate': completion_rate,
            'recent_checkins': len(recent_checkins)
        })

    return render_template('habit_stats.html', habit_stats=habit_stats)


@habits_bp.route('/categories', methods=['GET'])
@login_required
def get_categories():
    """获取所有分类"""
    categories = db.session.query(Habit.category).filter(
        Habit.user_id == current_user.id
    ).distinct().all()
    category_list = [c[0] for c in categories if c[0]]
    return jsonify(category_list)
