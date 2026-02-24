from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from models import db, DailyReflection

reflection_bp = Blueprint('reflection', __name__)


@reflection_bp.route('/daily')
@login_required
def daily_reflection():
    """每日复盘页面"""
    # 获取今天的复盘（如果存在）
    today = date.today()
    reflection = DailyReflection.query.filter_by(
        user_id=current_user.id,
        reflection_date=today
    ).first()

    return render_template('daily_reflection.html', reflection=reflection)


@reflection_bp.route('/save', methods=['POST'])
@login_required
def save_reflection():
    """保存每日复盘"""
    reflection_date_str = request.form.get('reflection_date')
    try:
        if reflection_date_str:
            reflection_date = datetime.strptime(reflection_date_str, '%Y-%m-%d').date()
        else:
            reflection_date = date.today()
    except:
        reflection_date = date.today()

    # 查找或创建复盘记录
    reflection = DailyReflection.query.filter_by(
        user_id=current_user.id,
        reflection_date=reflection_date
    ).first()

    if not reflection:
        reflection = DailyReflection(
            user_id=current_user.id,
            reflection_date=reflection_date
        )
        db.session.add(reflection)

    # 【1. 今日核心推进】
    reflection.core_progress = request.form.get('core_progress', '').strip()
    reflection.is_long_term_value = request.form.get('is_long_term_value') == 'on'

    # 【2. 深度工作】
    deep_hours = request.form.get('deep_work_hours', '').strip()
    reflection.deep_work_hours = float(deep_hours) if deep_hours else None
    reflection.high_energy_period = request.form.get('high_energy_period', '').strip()

    # 【3. 核心领悟】
    reflection.key_insight = request.form.get('key_insight', '').strip()
    reflection.changed_judgment = request.form.get('changed_judgment') == 'on'
    reflection.influences_future = request.form.get('influences_future') == 'on'

    # 【4. 偏差分析】
    reflection.time_waste = request.form.get('time_waste', '').strip()
    reflection.waste_reason = request.form.get('waste_reason', '').strip()

    # 【5. 明日唯一关键任务（MIT）】
    reflection.tomorrow_mit = request.form.get('tomorrow_mit', '').strip()

    try:
        db.session.commit()
        flash('复盘保存成功！', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'保存失败：{str(e)}', 'danger')

    return redirect(url_for('reflection.daily_reflection'))


@reflection_bp.route('/history')
@login_required
def reflection_history():
    """复盘历史记录"""
    page = request.args.get('page', 1, type=int)
    per_page = 10

    reflections = DailyReflection.query.filter_by(
        user_id=current_user.id
    ).order_by(
        DailyReflection.reflection_date.desc()
    ).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('reflection_history.html', reflections=reflections)


@reflection_bp.route('/stats')
@login_required
def reflection_stats():
    """复盘统计分析"""
    # 获取所有复盘记录
    reflections = DailyReflection.query.filter_by(
        user_id=current_user.id
    ).order_by(
        DailyReflection.reflection_date.desc()
    ).all()

    # 统计数据
    total_reflections = len(reflections)

    # 平均深度工作时间
    deep_work_list = [r.deep_work_hours for r in reflections if r.deep_work_hours]
    avg_deep_work = sum(deep_work_list) / len(deep_work_list) if deep_work_list else 0

    # 产生长期价值的比例
    long_term_count = sum(1 for r in reflections if r.is_long_term_value)
    long_term_ratio = long_term_count / total_reflections * 100 if total_reflections > 0 else 0

    # 改变判断的比例
    changed_judgment_count = sum(1 for r in reflections if r.changed_judgment)
    changed_judgment_ratio = changed_judgment_count / total_reflections * 100 if total_reflections > 0 else 0

    # 影响未来决策的比例
    influences_future_count = sum(1 for r in reflections if r.influences_future)
    influences_future_ratio = influences_future_count / total_reflections * 100 if total_reflections > 0 else 0

    stats = {
        'total_reflections': total_reflections,
        'avg_deep_work': round(avg_deep_work, 1),
        'long_term_ratio': round(long_term_ratio, 1),
        'changed_judgment_ratio': round(changed_judgment_ratio, 1),
        'influences_future_ratio': round(influences_future_ratio, 1),
        'recent_reflections': reflections[:7]  # 最近7条
    }

    return render_template('reflection_stats.html', stats=stats)
