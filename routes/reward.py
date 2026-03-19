from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from models import db, Reward, RewardProgress

reward_bp = Blueprint('reward', __name__)


@reward_bp.route('/')
@login_required
def list_rewards():
    """奖励列表"""
    # 获取所有奖励规则
    rewards = Reward.query.filter_by(
        user_id=current_user.id
    ).order_by(Reward.is_achieved.asc(), Reward.created_at.desc()).all()

    # 获取所有分类进度
    progress_list = RewardProgress.query.filter_by(
        user_id=current_user.id
    ).order_by(RewardProgress.total_hours.desc()).all()

    return render_template('reward.html', rewards=rewards, progress_list=progress_list)


@reward_bp.route('/add', methods=['POST'])
@login_required
def add_reward():
    """添加奖励规则"""
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    category = request.form.get('category', '').strip() or '其他'
    target_hours = float(request.form.get('target_hours', 0))

    if not title:
        flash('请输入奖励名称', 'danger')
        return redirect(url_for('reward.list_rewards'))

    reward = Reward(
        user_id=current_user.id,
        title=title,
        description=description,
        category=category,
        target_hours=target_hours
    )

    try:
        db.session.add(reward)
        db.session.commit()
        flash('奖励规则已添加', 'success')
    except Exception as e:
        db.session.rollback()
        flash('添加失败', 'danger')

    return redirect(url_for('reward.list_rewards'))


@reward_bp.route('/<int:reward_id>/achieve', methods=['POST'])
@login_required
def mark_achieved(reward_id):
    """标记奖励为已达成"""
    reward = Reward.query.filter_by(id=reward_id, user_id=current_user.id).first_or_404()

    reward.is_achieved = True
    reward.achieved_at = datetime.now()

    try:
        db.session.commit()
        flash(f'恭喜！「{reward.title}」已达成！', 'success')
    except Exception as e:
        db.session.rollback()
        flash('操作失败', 'danger')

    return redirect(url_for('reward.list_rewards'))


@reward_bp.route('/<int:reward_id>/redeem', methods=['POST'])
@login_required
def mark_redeemed(reward_id):
    """标记奖励为已兑现"""
    reward = Reward.query.filter_by(id=reward_id, user_id=current_user.id).first_or_404()

    reward.is_redeemed = True

    try:
        db.session.commit()
        flash(f'「{reward.title}」已兑现！', 'success')
    except Exception as e:
        db.session.rollback()
        flash('操作失败', 'danger')

    return redirect(url_for('reward.list_rewards'))


@reward_bp.route('/<int:reward_id>/delete', methods=['POST'])
@login_required
def delete_reward(reward_id):
    """删除奖励规则"""
    reward = Reward.query.filter_by(id=reward_id, user_id=current_user.id).first_or_404()

    try:
        db.session.delete(reward)
        db.session.commit()
        flash('奖励规则已删除', 'success')
    except Exception as e:
        db.session.rollback()
        flash('删除失败', 'danger')

    return redirect(url_for('reward.list_rewards'))


@reward_bp.route('/progress')
@login_required
def get_progress():
    """获取各分类进度"""
    progress_list = RewardProgress.query.filter_by(
        user_id=current_user.id
    ).all()

    data = []
    for progress in progress_list:
        # 计算相关奖励
        related_rewards = Reward.query.filter_by(
            user_id=current_user.id,
            category=progress.category,
            is_achieved=False
        ).all()

        for reward in related_rewards:
            data.append({
                'category': progress.category,
                'current_hours': round(progress.total_hours, 1),
                'target_hours': reward.target_hours,
                'reward_title': reward.title,
                'progress_percent': round(progress.total_hours / reward.target_hours * 100, 1) if reward.target_hours > 0 else 0
            })

    return jsonify(data)


@reward_bp.route('/check-achievements', methods=['POST'])
@login_required
def check_achievements():
    """检查并更新奖励达成状态"""
    # 获取所有未达成的奖励
    rewards = Reward.query.filter_by(
        user_id=current_user.id,
        is_achieved=False
    ).all()

    newly_achieved = []

    for reward in rewards:
        # 获取对应分类的进度
        progress = RewardProgress.query.filter_by(
            user_id=current_user.id,
            category=reward.category
        ).first()

        if progress and progress.total_hours >= reward.target_hours:
            reward.is_achieved = True
            reward.achieved_at = datetime.now()
            newly_achieved.append(reward.title)

    if newly_achieved:
        try:
            db.session.commit()
            flash(f'恭喜达成了 {len(newly_achieved)} 个奖励！', 'success')
        except Exception as e:
            db.session.rollback()
    else:
        flash('暂无新奖励达成', 'info')

    return redirect(url_for('reward.list_rewards'))
