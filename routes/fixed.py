from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from sqlalchemy import and_, or_
from models import db, FixedSchedule, ImportantDate

fixed_bp = Blueprint('fixed', __name__)


# ==================== 固定日程 ====================

@fixed_bp.route('/schedules')
@login_required
def list_schedules():
    """固定日程列表"""
    schedules = FixedSchedule.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).order_by(FixedSchedule.day_of_week, FixedSchedule.start_time).all()

    return render_template('fixed_schedules.html', schedules=schedules)


@fixed_bp.route('/schedules/add', methods=['POST'])
@login_required
def add_schedule():
    """添加固定日程"""
    schedule = FixedSchedule(user_id=current_user.id)

    # 基本信息
    schedule.title = request.form.get('title', '').strip()
    schedule.description = request.form.get('description', '').strip()
    schedule.category = request.form.get('category', '其他').strip() or '其他'
    schedule.location = request.form.get('location', '').strip()

    # 时间设置
    schedule.day_of_week = int(request.form.get('day_of_week'))
    start_time_str = request.form.get('start_time', '')
    end_time_str = request.form.get('end_time', '')

    try:
        schedule.start_time = datetime.strptime(start_time_str, '%H:%M').time()
        schedule.end_time = datetime.strptime(end_time_str, '%H:%M').time()
    except:
        flash('请输入正确的时间格式', 'danger')
        return redirect(url_for('fixed.list_schedules'))

    # 时间范围
    start_date_str = request.form.get('start_date', '')
    if start_date_str:
        try:
            schedule.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except:
            schedule.start_date = date.today()
    else:
        schedule.start_date = date.today()

    end_date_str = request.form.get('end_date', '')
    if end_date_str:
        try:
            schedule.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except:
            schedule.end_date = None

    # 提醒
    schedule.reminder_minutes = int(request.form.get('reminder_minutes', 30))
    schedule.color = request.form.get('color', 'primary')

    try:
        db.session.add(schedule)
        db.session.commit()
        flash('固定日程创建成功', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'创建失败：{str(e)}', 'danger')

    return redirect(url_for('fixed.list_schedules'))


@fixed_bp.route('/schedules/<int:schedule_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_schedule(schedule_id):
    """编辑固定日程"""
    schedule = FixedSchedule.query.filter_by(id=schedule_id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        # 基本信息
        schedule.title = request.form.get('title', '').strip()
        schedule.description = request.form.get('description', '').strip()
        schedule.category = request.form.get('category', '其他').strip() or '其他'
        schedule.location = request.form.get('location', '').strip()

        # 时间设置
        schedule.day_of_week = int(request.form.get('day_of_week'))
        start_time_str = request.form.get('start_time', '')
        end_time_str = request.form.get('end_time', '')

        try:
            schedule.start_time = datetime.strptime(start_time_str, '%H:%M').time()
            schedule.end_time = datetime.strptime(end_time_str, '%H:%M').time()
        except:
            flash('请输入正确的时间格式', 'danger')
            return redirect(url_for('fixed.edit_schedule', schedule_id=schedule_id))

        # 时间范围
        start_date_str = request.form.get('start_date', '')
        if start_date_str:
            try:
                schedule.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except:
                pass

        end_date_str = request.form.get('end_date', '')
        if end_date_str:
            try:
                schedule.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except:
                schedule.end_date = None

        # 提醒
        schedule.reminder_minutes = int(request.form.get('reminder_minutes', 30))
        schedule.color = request.form.get('color', 'primary')

        try:
            db.session.commit()
            flash('固定日程更新成功', 'success')
            return redirect(url_for('fixed.list_schedules'))
        except Exception as e:
            db.session.rollback()
            flash(f'更新失败：{str(e)}', 'danger')

    return render_template('fixed_schedule_form.html', schedule=schedule)


@fixed_bp.route('/schedules/<int:schedule_id>/toggle', methods=['POST'])
@login_required
def toggle_schedule(schedule_id):
    """启用/禁用固定日程"""
    schedule = FixedSchedule.query.filter_by(id=schedule_id, user_id=current_user.id).first_or_404()

    schedule.is_active = not schedule.is_active

    try:
        db.session.commit()
        status = '启用' if schedule.is_active else '禁用'
        flash(f'固定日程已{status}', 'success')
    except Exception as e:
        db.session.rollback()
        flash('操作失败', 'danger')

    return redirect(url_for('fixed.list_schedules'))


@fixed_bp.route('/schedules/<int:schedule_id>/delete', methods=['POST'])
@login_required
def delete_schedule(schedule_id):
    """删除固定日程"""
    schedule = FixedSchedule.query.filter_by(id=schedule_id, user_id=current_user.id).first_or_404()

    try:
        db.session.delete(schedule)
        db.session.commit()
        flash('固定日程已删除', 'success')
    except Exception as e:
        db.session.rollback()
        flash('删除失败', 'danger')

    return redirect(url_for('fixed.list_schedules'))


@fixed_bp.route('/schedules/week')
@login_required
def week_schedule():
    """本周固定日程视图"""
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    # 获取本周的固定日程
    schedules = FixedSchedule.query.filter(
        FixedSchedule.user_id == current_user.id,
        FixedSchedule.is_active == True,
        FixedSchedule.start_date <= end_of_week,
        or_(FixedSchedule.end_date == None, FixedSchedule.end_date >= start_of_week)
    ).all()

    # 构建周日程
    week_days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    week_schedules = {i: [] for i in range(7)}

    for schedule in schedules:
        week_schedules[schedule.day_of_week].append(schedule)

    return render_template('fixed_week.html',
                         week_days=week_days,
                         week_schedules=week_schedules,
                         start_of_week=start_of_week,
                         end_of_week=end_of_week)


# ==================== 重要日子 ====================

@fixed_bp.route('/dates')
@login_required
def list_dates():
    """重要日子列表"""
    # 按日期排序获取即将到来的日子
    today = date.today()
    dates = ImportantDate.query.filter_by(
        user_id=current_user.id
    ).filter(
        or_(ImportantDate.event_date >= today, ImportantDate.is_recurring == True)
    ).order_by(ImportantDate.event_date).all()

    # 分为即将到来的和重复的
    upcoming = []
    recurring = []

    for d in dates:
        if d.is_recurring:
            recurring.append(d)
        elif d.event_date >= today:
            upcoming.append(d)

    return render_template('important_dates.html', upcoming=upcoming, recurring=recurring)


@fixed_bp.route('/dates/add', methods=['POST'])
@login_required
def add_date():
    """添加重要日子"""
    imp_date = ImportantDate(user_id=current_user.id)

    # 基本信息
    imp_date.title = request.form.get('title', '').strip()
    imp_date.description = request.form.get('description', '').strip()
    imp_date.date_type = request.form.get('date_type', 'other')
    imp_date.color = request.form.get('color', 'info')

    # 日期时间
    event_date_str = request.form.get('event_date', '')
    if event_date_str:
        try:
            imp_date.event_date = datetime.strptime(event_date_str, '%Y-%m-%d').date()
        except:
            flash('请输入正确的日期格式', 'danger')
            return redirect(url_for('fixed.list_dates'))

    event_time_str = request.form.get('event_time', '')
    if event_time_str:
        try:
            imp_date.event_time = datetime.strptime(event_time_str, '%H:%M').time()
        except:
            imp_date.event_time = None

    # 提醒
    imp_date.remind_days_before = int(request.form.get('remind_days_before', 0))

    try:
        db.session.add(imp_date)
        db.session.commit()
        flash('重要日子添加成功', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'添加失败：{str(e)}', 'danger')

    return redirect(url_for('fixed.list_dates'))


@fixed_bp.route('/dates/<int:date_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_date(date_id):
    """编辑重要日子"""
    imp_date = ImportantDate.query.filter_by(id=date_id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        # 基本信息
        imp_date.title = request.form.get('title', '').strip()
        imp_date.description = request.form.get('description', '').strip()
        imp_date.date_type = request.form.get('date_type', 'other')
        imp_date.color = request.form.get('color', 'info')

        # 日期时间
        event_date_str = request.form.get('event_date', '')
        if event_date_str:
            try:
                imp_date.event_date = datetime.strptime(event_date_str, '%Y-%m-%d').date()
            except:
                pass

        event_time_str = request.form.get('event_time', '')
        if event_time_str:
            try:
                imp_date.event_time = datetime.strptime(event_time_str, '%H:%M').time()
            except:
                imp_date.event_time = None
        else:
            imp_date.event_time = None

        # 提醒
        imp_date.remind_days_before = int(request.form.get('remind_days_before', 0))

        try:
            db.session.commit()
            flash('重要日子更新成功', 'success')
            return redirect(url_for('fixed.list_dates'))
        except Exception as e:
            db.session.rollback()
            flash(f'更新失败：{str(e)}', 'danger')

    return render_template('important_date_form.html', imp_date=imp_date)


@fixed_bp.route('/dates/<int:date_id>/complete', methods=['POST'])
@login_required
def complete_date(date_id):
    """标记重要日子为已完成"""
    imp_date = ImportantDate.query.filter_by(id=date_id, user_id=current_user.id).first_or_404()

    imp_date.is_completed = not imp_date.is_completed

    try:
        db.session.commit()
        status = '已完成' if imp_date.is_completed else '未完成'
        flash(f'已标记为{status}', 'success')
    except Exception as e:
        db.session.rollback()
        flash('操作失败', 'danger')

    return redirect(url_for('fixed.list_dates'))


@fixed_bp.route('/dates/<int:date_id>/delete', methods=['POST'])
@login_required
def delete_date(date_id):
    """删除重要日子"""
    imp_date = ImportantDate.query.filter_by(id=date_id, user_id=current_user.id).first_or_404()

    try:
        db.session.delete(imp_date)
        db.session.commit()
        flash('重要日子已删除', 'success')
    except Exception as e:
        db.session.rollback()
        flash('删除失败', 'danger')

    return redirect(url_for('fixed.list_dates'))


@fixed_bp.route('/dates/calendar')
@login_required
def dates_calendar():
    """日历视图 - 显示本月重要日子"""
    from calendar import monthrange
    today = date.today()
    now = datetime.now()
    year = int(request.args.get('year', today.year))
    month = int(request.args.get('month', today.month))

    # 计算导航月份
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    # 获取本月的重要日子
    start_of_month = date(year, month, 1)
    end_of_month = date(year, month, monthrange(year, month)[1])

    dates = ImportantDate.query.filter(
        ImportantDate.user_id == current_user.id,
        ImportantDate.event_date >= start_of_month,
        ImportantDate.event_date <= end_of_month
    ).all()

    # 按日期组织
    dates_by_day = {}
    for d in dates:
        day = d.event_date.day
        if day not in dates_by_day:
            dates_by_day[day] = []
        dates_by_day[day].append(d)

    # 计算日历相关值
    start_weekday = start_of_month.weekday()  # 0=周一, 6=周日
    days_in_month = monthrange(year, month)[1]

    return render_template('dates_calendar.html',
                         year=year,
                         month=month,
                         prev_year=prev_year,
                         prev_month=prev_month,
                         next_year=next_year,
                         next_month=next_month,
                         dates_by_day=dates_by_day,
                         start_weekday=start_weekday,
                         days_in_month=days_in_month,
                         now=now)


@fixed_bp.route('/upcoming')
@login_required
def upcoming_events():
    """获取即将到来的事件（用于仪表盘）"""
    today = date.today()
    upcoming_days = 7  # 显示未来7天

    # 重要日子
    important_dates = ImportantDate.query.filter(
        ImportantDate.user_id == current_user.id,
        ImportantDate.event_date >= today,
        ImportantDate.event_date <= today + timedelta(days=upcoming_days)
    ).order_by(ImportantDate.event_date).limit(5).all()

    # 固定日程（本周）
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    today_weekday = today.weekday()
    today_schedules = FixedSchedule.query.filter(
        FixedSchedule.user_id == current_user.id,
        FixedSchedule.is_active == True,
        FixedSchedule.day_of_week == today_weekday,
        FixedSchedule.start_date <= today,
        or_(FixedSchedule.end_date == None, FixedSchedule.end_date >= today)
    ).order_by(FixedSchedule.start_time).all()

    return jsonify({
        'important_dates': [{'title': d.title, 'date': d.event_date.isoformat(), 'type': d.date_type}
                             for d in important_dates],
        'today_schedules': [{'title': s.title, 'start': s.start_time.strftime('%H:%M'),
                              'end': s.end_time.strftime('%H:%M'), 'location': s.location}
                             for s in today_schedules]
    })
