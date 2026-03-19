from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from models import db, Task, Schedule, Feedback

def check_task_status_by_deadline(task):
    """根据时间期限检查任务状态（精确到天，手动完成优先）
    
    规则：
    1. 如果用户手动点击"完成"按钮（completed_at 有值），保持 completed 状态
    2. 如果是自动判断的：
       - deadline 已过（今天日期 > deadline日期），标记为 completed
       - deadline 未到（今天日期 <= deadline日期），标记为 pending
    
    用户可以通过修改 deadline 来改变非手动完成的任务状态：
    - 延长 deadline 到未来 → 任务变回 pending
    - 缩短 deadline 到过去 → 任务变为 completed
    """
    if not task.deadline:
        return False
    
    # 如果用户手动完成（通过按钮），不自动改变状态
    # 除非用户修改了 deadline
    if task.status == 'completed' and task.completed_at:
        # 检查是否需要根据新的 deadline 改回 pending
        today = datetime.now().date()
        deadline_date = task.deadline.date() if hasattr(task.deadline, 'date') else task.deadline
        
        # 只有当 deadline 改到未来，才允许从 completed 改回 pending
        if today <= deadline_date:
            # 用户延长了 deadline，允许变回 pending
            task.status = 'pending'
            # 保留 completed_at 作为历史记录，或者清空
            # 这里清空，因为已经不是完成状态
            task.completed_at = None
            return True
        return False
    
    # 自动判断逻辑（精确到天）
    today = datetime.now().date()
    deadline_date = task.deadline.date() if hasattr(task.deadline, 'date') else task.deadline
    
    if today > deadline_date:
        # deadline 已过（以天为单位），应该已完成
        if task.status != 'completed':
            task.status = 'completed'
            # 自动完成的不设置 completed_at，或者设置一个标记
            # 这里设置 completed_at 但后续判断时会根据 deadline 变化改回
            task.completed_at = datetime.now()
            return True
    else:
        # deadline 未到（以天为单位），应该未完成
        if task.status != 'pending':
            task.status = 'pending'
            task.completed_at = None
            return True
    return False

def get_task_actual_hours(task):
    """获取任务的实际已完成时长"""
    total_hours = 0
    schedules = Schedule.query.filter_by(task_id=task.id).all()
    for sched in schedules:
        if sched.status == 'completed':
            # 计算日程时长
            duration = (datetime.combine(sched.date, sched.end_time) - 
                       datetime.combine(sched.date, sched.start_time)).total_seconds() / 3600
            total_hours += duration
    return total_hours

def check_task_status_by_hours(task):
    """根据预计耗时检查任务状态（手动完成优先）
    
    规则：
    1. 如果用户手动点击"完成"按钮（completed_at 有值），保持 completed 状态
    2. 如果是自动判断的：
       - 实际耗时 >= estimated_hours，标记为 completed
       - 实际耗时 < estimated_hours，标记为 pending
    """
    # 如果用户手动完成，不自动改变
    if task.status == 'completed' and task.completed_at:
        return False
    
    actual_hours = get_task_actual_hours(task)
    if actual_hours >= task.estimated_hours:
        if task.status != 'completed':
            task.status = 'completed'
            task.completed_at = datetime.now()
            return True
    else:
        # 实际耗时不足，如果之前是自动完成的，改回 pending
        if task.status == 'completed':
            task.status = 'pending'
            task.completed_at = None
            return True
    return False

def update_task_status(task):
    """综合判断任务状态
    
    优先级：
    1. 如果有 deadline，优先根据 deadline 判断
    2. 如果没有 deadline，根据 estimated_hours 判断
    """
    if task.deadline:
        return check_task_status_by_deadline(task)
    else:
        return check_task_status_by_hours(task)

tasks_bp = Blueprint('tasks', __name__)

@tasks_bp.route('/')
@login_required
def list_tasks():
    """任务列表"""
    # 获取筛选参数
    status_filter = request.args.get('status', '')
    priority_filter = request.args.get('priority', '')
    category_filter = request.args.get('category', '')
    sort_by = request.args.get('sort', 'deadline')

    # 先获取所有任务（不过滤状态，因为要自动更新）
    all_tasks = Task.query.filter_by(user_id=current_user.id).all()
    
    # 自动更新所有任务状态
    has_changes = False
    for task in all_tasks:
        if update_task_status(task):
            has_changes = True
    
    if has_changes:
        db.session.commit()
        flash('部分任务状态已根据时间期限/耗时自动更新', 'info')

    # 重新构建查询（可能已经提交，需要重新查询）
    query = Task.query.filter_by(user_id=current_user.id)

    if status_filter:
        query = query.filter_by(status=status_filter)
    if priority_filter:
        query = query.filter_by(priority=priority_filter)
    if category_filter:
        query = query.filter_by(category=category_filter)

    # 排序
    if sort_by == 'deadline':
        query = query.order_by(Task.deadline.asc().nullslast())
    elif sort_by == 'priority':
        priority_order = {'高': 0, '中': 1, '低': 2}
        # 使用case表达式进行排序
        query = query.order_by(db.case(priority_order, value=Task.priority))
    elif sort_by == 'created':
        query = query.order_by(Task.created_at.desc())

    tasks = query.all()

    # 获取所有分类（用于筛选）
    categories = db.session.query(Task.category).filter(
        Task.user_id == current_user.id
    ).distinct().all()
    categories = [c[0] for c in categories]

    return render_template('task_list.html',
                         tasks=tasks,
                         categories=categories,
                         status_filter=status_filter,
                         priority_filter=priority_filter,
                         category_filter=category_filter,
                         sort_by=sort_by)


@tasks_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_task():
    """创建新任务"""
    if request.method == 'POST':
        task = Task(user_id=current_user.id)

        # 基本信息
        task.title = request.form.get('title', '').strip()
        task.description = request.form.get('description', '').strip()
        task.estimated_hours = float(request.form.get('estimated_hours', 1))
        task.priority = request.form.get('priority', '中')
        task.category = request.form.get('category', '其他').strip() or '其他'

        # 会议设置
        task.is_meeting = request.form.get('is_meeting') == 'on'
        task.location = request.form.get('location', '').strip()

        # 截止日期
        deadline_str = request.form.get('deadline', '')
        if deadline_str:
            try:
                task.deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
            except:
                task.deadline = None
        else:
            task.deadline = None
        
        # 自动更新任务状态（根据 deadline 和耗时）
        update_task_status(task)

        # 重复设置
        is_recurring = request.form.get('is_recurring') == 'on'
        task.is_recurring = is_recurring

        if is_recurring:
            task.recurring_type = request.form.get('recurring_type', 'daily')
            if task.recurring_type == 'weekly_days':
                days = request.form.getlist('recurring_days')
                task.recurring_days = ','.join(days)

            recurring_end = request.form.get('recurring_end_date', '')
            if recurring_end:
                try:
                    task.recurring_end_date = datetime.strptime(recurring_end, '%Y-%m-%d')
                except:
                    task.recurring_end_date = None

        try:
            db.session.add(task)
            db.session.commit()
            flash('任务创建成功！<a href="{}" class="alert-link">点击这里</a>更新日程安排'.format(url_for('schedule.view_schedule')), 'success')
            return redirect(url_for('tasks.list_tasks'))
        except Exception as e:
            db.session.rollback()
            flash(f'创建失败：{str(e)}', 'danger')

    return render_template('task_form.html', task=None)


@tasks_bp.route('/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    """编辑任务"""
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        # 基本信息
        task.title = request.form.get('title', '').strip()
        task.description = request.form.get('description', '').strip()
        task.estimated_hours = float(request.form.get('estimated_hours', 1))
        task.priority = request.form.get('priority', '中')
        task.category = request.form.get('category', '其他').strip() or '其他'

        # 会议设置
        task.is_meeting = request.form.get('is_meeting') == 'on'
        task.location = request.form.get('location', '').strip()

        # 截止日期
        deadline_str = request.form.get('deadline', '')
        if deadline_str:
            try:
                task.deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
            except:
                task.deadline = None
        else:
            task.deadline = None

        # 重复设置
        is_recurring = request.form.get('is_recurring') == 'on'
        task.is_recurring = is_recurring

        if is_recurring:
            task.recurring_type = request.form.get('recurring_type', 'daily')
            if task.recurring_type == 'weekly_days':
                days = request.form.getlist('recurring_days')
                task.recurring_days = ','.join(days)

            recurring_end = request.form.get('recurring_end_date', '')
            if recurring_end:
                try:
                    task.recurring_end_date = datetime.strptime(recurring_end, '%Y-%m-%d')
                except:
                    task.recurring_end_date = None
        else:
            task.recurring_type = None
            task.recurring_days = None
            task.recurring_end_date = None
        
        # 自动更新任务状态（根据 deadline 和耗时）
        update_task_status(task)

        try:
            db.session.commit()
            flash('任务更新成功（状态已根据时间期限/耗时自动更新）', 'success')
            return redirect(url_for('tasks.list_tasks'))
        except Exception as e:
            db.session.rollback()
            flash(f'更新失败：{str(e)}', 'danger')

    return render_template('task_form.html', task=task)


@tasks_bp.route('/<int:task_id>/complete', methods=['POST'])
@login_required
def complete_task(task_id):
    """标记任务完成"""
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()

    task.status = 'completed'
    task.completed_at = datetime.now()

    try:
        db.session.commit()
        flash('任务已标记为完成', 'success')
    except Exception as e:
        db.session.rollback()
        flash('操作失败', 'danger')

    return redirect(url_for('tasks.list_tasks'))


@tasks_bp.route('/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    """删除任务"""
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()

    try:
        db.session.delete(task)
        db.session.commit()
        flash('任务已删除', 'success')
    except Exception as e:
        db.session.rollback()
        flash('删除失败', 'danger')

    return redirect(url_for('tasks.list_tasks'))


@tasks_bp.route('/categories', methods=['GET'])
@login_required
def get_categories():
    """获取所有分类（用于自动完成）"""
    categories = db.session.query(Task.category).filter(
        Task.user_id == current_user.id
    ).distinct().all()
    category_list = [c[0] for c in categories if c[0]]
    return jsonify(category_list)
