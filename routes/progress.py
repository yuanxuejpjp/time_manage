from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from sqlalchemy import and_, func
from models import db, User, Habit, HabitCheckin, Reward, PointsHistory, RewardProgress

progress_bp = Blueprint('progress', __name__)


@progress_bp.route('/progress')
@login_required
def progress_center():
    """统一进度中心 - 习惯打卡与奖励积分"""
    # 获取用户信息
    user = User.query.get(current_user.id)

    # 获取所有活跃习惯
    habits = Habit.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).all()

    # 今天的习惯状态
    today = date.today()
    today_habits = []
    for habit in habits:
        if habit.should_do_today():
            checkin = habit.get_today_checkin()
            today_habits.append({
                'habit': habit,
                'checked': checkin is not None,
                'streak': habit.get_current_streak(),
                'checkin_id': checkin.id if checkin else None
            })

    # 获取分类进度
    category_progress = RewardProgress.query.filter_by(
        user_id=current_user.id
    ).order_by(RewardProgress.total_points.desc()).all()

    # 可兑换的奖励
    available_rewards = Reward.query.filter_by(
        user_id=current_user.id,
        is_redeemed=False
    ).order_by(Reward.points_required.asc()).all()

    # 已兑换的奖励
    redeemed_rewards = Reward.query.filter_by(
        user_id=current_user.id,
        is_redeemed=True
    ).order_by(Reward.redeemed_at.desc()).limit(5).all()

    # 最近积分历史
    recent_history = PointsHistory.query.filter_by(
        user_id=current_user.id
    ).order_by(PointsHistory.created_at.desc()).limit(10).all()

    # 统计数据
    total_checkins = sum(h.total_checkins for h in habits)
    total_points_earned = db.session.query(func.sum(PointsHistory.points_change)).filter(
        PointsHistory.user_id == current_user.id,
        PointsHistory.points_change > 0
    ).scalar() or 0

    return render_template('progress.html',
                         user=user,
                         today_habits=today_habits,
                         category_progress=category_progress,
                         available_rewards=available_rewards,
                         redeemed_rewards=redeemed_rewards,
                         recent_history=recent_history,
                         total_checkins=total_checkins,
                         total_points_earned=total_points_earned)


@progress_bp.route('/habits/<int:habit_id>/checkin', methods=['POST'])
@login_required
def habit_checkin(habit_id):
    """习惯打卡 - 获得积分"""
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()

    # 检查今天是否已打卡
    today = date.today()
    existing = HabitCheckin.query.filter_by(
        habit_id=habit_id,
        checkin_date=today
    ).first()

    if existing:
        flash('今天已经打过卡了', 'warning')
        return redirect(url_for('progress.progress_center'))

    # 创建打卡记录
    checkin = HabitCheckin(
        user_id=current_user.id,
        habit_id=habit_id,
        checkin_date=today,
        actual_value=float(request.form.get('actual_value', habit.target_value))
    )
    checkin.notes = request.form.get('notes', '')

    # 获得积分
    points = habit.points_value
    user = User.query.get(current_user.id)
    user.total_points += points

    # 更新分类进度
    category_prog = RewardProgress.query.filter_by(
        user_id=current_user.id,
        category=habit.category
    ).first()
    if not category_prog:
        category_prog = RewardProgress(
            user_id=current_user.id,
            category=habit.category
        )
        db.session.add(category_prog)
    category_prog.total_points += points
    category_prog.checkin_count += 1
    category_prog.last_updated = datetime.now()

    # 记录积分历史
    history = PointsHistory(
        user_id=current_user.id,
        points_change=points,
        source_type='habit_checkin',
        source_id=habit_id,
        description=f'完成习惯「{habit.title}」',
        balance_after=user.total_points
    )

    # 更新习惯统计
    habit.total_checkins += 1
    habit.streak_days = habit.get_current_streak() + 1
    habit.updated_at = datetime.now()

    try:
        db.session.add(checkin)
        db.session.add(history)
        db.session.commit()
        flash(f'打卡成功！获得 {points} 积分', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'打卡失败：{str(e)}', 'danger')

    return redirect(url_for('progress.progress_center'))


@progress_bp.route('/habits/<int:habit_id>/undo', methods=['POST'])
@login_required
def habit_undo(habit_id):
    """撤销打卡 - 退回积分"""
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()

    # 查找今天的打卡记录
    today = date.today()
    checkin = HabitCheckin.query.filter_by(
        habit_id=habit_id,
        checkin_date=today
    ).first()

    if not checkin:
        flash('今天还没有打卡记录', 'warning')
        return redirect(url_for('progress.progress_center'))

    # 计算要退回的积分
    points = habit.points_value
    user = User.query.get(current_user.id)

    # 确保积分足够
    if user.total_points < points:
        flash('当前积分不足以撤销', 'danger')
        return redirect(url_for('progress.progress_center'))

    # 退回积分
    user.total_points -= points

    # 更新分类进度
    category_prog = RewardProgress.query.filter_by(
        user_id=current_user.id,
        category=habit.category
    ).first()
    if category_prog:
        category_prog.total_points = max(0, category_prog.total_points - points)
        category_prog.checkin_count = max(0, category_prog.checkin_count - 1)
        category_prog.last_updated = datetime.now()

    # 记录积分历史
    history = PointsHistory(
        user_id=current_user.id,
        points_change=-points,
        source_type='habit_checkin',
        source_id=habit_id,
        description=f'撤销打卡「{habit.title}」',
        balance_after=user.total_points
    )

    # 更新习惯统计
    habit.total_checkins = max(0, habit.total_checkins - 1)
    habit.streak_days = max(0, habit.streak_days - 1)
    habit.updated_at = datetime.now()

    try:
        db.session.delete(checkin)
        db.session.add(history)
        db.session.commit()
        flash(f'已撤销打卡，退回 {points} 积分', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'撤销失败：{str(e)}', 'danger')

    return redirect(url_for('progress.progress_center'))


@progress_bp.route('/rewards/add', methods=['POST'])
@login_required
def add_reward():
    """添加新奖励"""
    reward = Reward(user_id=current_user.id)

    reward.title = request.form.get('title', '').strip()
    reward.description = request.form.get('description', '').strip()
    reward.points_required = int(request.form.get('points_required', 100))
    reward.icon = request.form.get('icon', 'gift')

    try:
        db.session.add(reward)
        db.session.commit()
        flash('奖励添加成功', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'添加失败：{str(e)}', 'danger')

    return redirect(url_for('progress.progress_center'))


@progress_bp.route('/rewards/<int:reward_id>/redeem', methods=['POST'])
@login_required
def redeem_reward(reward_id):
    """兑换奖励"""
    reward = Reward.query.filter_by(id=reward_id, user_id=current_user.id).first_or_404()

    if reward.is_redeemed:
        flash('该奖励已兑换', 'warning')
        return redirect(url_for('progress.progress_center'))

    user = User.query.get(current_user.id)

    if user.total_points < reward.points_required:
        flash(f'积分不足，需要 {reward.points_required} 积分', 'danger')
        return redirect(url_for('progress.progress_center'))

    # 扣除积分
    user.total_points -= reward.points_required

    # 标记为已兑换
    reward.is_redeemed = True
    reward.redeemed_at = datetime.now()

    # 记录积分历史
    history = PointsHistory(
        user_id=current_user.id,
        points_change=-reward.points_required,
        source_type='reward_redeem',
        source_id=reward_id,
        description=f'兑换奖励「{reward.title}」',
        balance_after=user.total_points
    )

    try:
        db.session.add(history)
        db.session.commit()
        flash(f'兑换成功！消耗 {reward.points_required} 积分', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'兑换失败：{str(e)}', 'danger')

    return redirect(url_for('progress.progress_center'))


@progress_bp.route('/rewards/<int:reward_id>/delete', methods=['POST'])
@login_required
def delete_reward(reward_id):
    """删除奖励"""
    reward = Reward.query.filter_by(id=reward_id, user_id=current_user.id).first_or_404()

    if reward.is_redeemed:
        flash('已兑换的奖励不能删除', 'warning')
        return redirect(url_for('progress.progress_center'))

    try:
        db.session.delete(reward)
        db.session.commit()
        flash('奖励已删除', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'删除失败：{str(e)}', 'danger')

    return redirect(url_for('progress.progress_center'))


@progress_bp.route('/api/points-stats')
@login_required
def points_stats_api():
    """积分统计API - 用于图表"""
    # 按分类统计积分
    category_stats = db.session.query(
        RewardProgress.category,
        RewardProgress.total_points,
        RewardProgress.checkin_count
    ).filter_by(user_id=current_user.id).all()

    # 最近7天积分变化
    today = date.today()
    daily_points = []
    for i in range(7):
        day = today - timedelta(days=6-i)
        points = db.session.query(func.sum(PointsHistory.points_change)).filter(
            PointsHistory.user_id == current_user.id,
            PointsHistory.points_change > 0,
            func.date(PointsHistory.created_at) == day
        ).scalar() or 0
        daily_points.append({
            'date': day.strftime('%m-%d'),
            'points': points
        })

    return jsonify({
        'category_stats': [
            {'category': c.category, 'points': c.total_points, 'count': c.checkin_count}
            for c in category_stats
        ],
        'daily_points': daily_points
    })
