from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from models import db, Task

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

    # 构建查询
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

        try:
            db.session.commit()
            flash('任务更新成功', 'success')
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
