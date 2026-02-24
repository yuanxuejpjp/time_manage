from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date
import requests
import json
from models import db, Summary, Schedule, Feedback, Task, DailyReflection
from sqlalchemy import func, and_

summary_bp = Blueprint('summary', __name__)


def call_deepseek_api(prompt, max_tokens=2000):
    """调用DeepSeek API"""
    api_key = current_app.config.get('DEEPSEEK_API_KEY', '')
    base_url = current_app.config.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')

    if not api_key:
        print('DeepSeek API key not configured')
        return None

    try:
        # 禁用代理，避免系统代理干扰
        session = requests.Session()
        session.trust_env = False  # 忽略系统代理设置

        response = session.post(
            f'{base_url}/v1/chat/completions',
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            },
            json={
                'model': 'deepseek-chat',
                'messages': [
                    {'role': 'system', 'content': '你是一个专业的效率分析师，擅长分析时间使用数据并给出实用建议。'},
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': max_tokens,
                'temperature': 0.7
            },
            timeout=60,
            verify=True
        )

        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            print(f'DeepSeek API error: {response.status_code} - {response.text}')
            return None

    except requests.exceptions.ProxyError as e:
        print(f'DeepSeek API proxy error: {str(e)}')
        print('提示：请检查系统代理设置或尝试关闭代理')
        return None
    except requests.exceptions.SSLError as e:
        print(f'DeepSeek API SSL error: {str(e)}')
        print('提示：SSL连接失败，可能需要配置VPN或检查网络')
        return None
    except requests.exceptions.Timeout as e:
        print(f'DeepSeek API timeout: {str(e)}')
        print('提示：连接超时，请检查网络或稍后重试')
        return None
    except Exception as e:
        print(f'DeepSeek API exception: {type(e).__name__}: {str(e)}')
        return None


@summary_bp.route('/')
@login_required
def list_summaries():
    """查看所有总结"""
    summaries = Summary.query.filter_by(
        user_id=current_user.id
    ).order_by(Summary.created_at.desc()).all()

    return render_template('summary_list.html', summaries=summaries)


@summary_bp.route('/generate', methods=['POST'])
@login_required
def generate_summary():
    """生成总结"""
    summary_type = request.form.get('type', 'daily')  # daily, weekly, monthly

    # 确定日期范围
    today = datetime.now().date()

    if summary_type == 'daily':
        start_date = today
        end_date = today
        title = f"日报 - {today.strftime('%Y年%m月%d日')}"
    elif summary_type == 'weekly':
        # 本周一到今天
        start_date = today - timedelta(days=today.weekday())
        end_date = today
        title = f"周报 - {start_date.strftime('%m月%d日')} 至 {end_date.strftime('%m月%d日')}"
    else:  # monthly
        # 本月1号到今天
        start_date = today.replace(day=1)
        end_date = today
        title = f"月报 - {today.strftime('%Y年%m月')}"

    # 检查是否已存在
    existing = Summary.query.filter_by(
        user_id=current_user.id,
        summary_type=summary_type,
        start_date=start_date,
        end_date=end_date
    ).first()

    if existing:
        flash(f'{title}已存在，正在更新...', 'info')
        summary = existing
    else:
        summary = Summary(
            user_id=current_user.id,
            summary_type=summary_type,
            start_date=start_date,
            end_date=end_date
        )
        db.session.add(summary)

    # 获取日程数据
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())

    schedules = Schedule.query.filter(
        Schedule.user_id == current_user.id,
        Schedule.date.between(start_date, end_date)
    ).all()

    # 获取反馈数据
    schedule_ids = [s.id for s in schedules]
    feedbacks = Feedback.query.filter(
        Feedback.schedule_id.in_(schedule_ids)
    ).all() if schedule_ids else []

    # 构建反馈字典，方便快速查找
    feedback_dict = {fb.schedule_id: fb for fb in feedbacks}

    # 统计数据
    total_tasks = len(schedules)
    completed_tasks = len([s for s in schedules if s.status == 'completed'])
    summary.total_tasks = total_tasks
    summary.completed_tasks = completed_tasks
    summary.completion_rate = round(completed_tasks / total_tasks * 100, 1) if total_tasks > 0 else 0

    # 计算总时长和分类统计 - 优先使用反馈中的实际时长，否则使用日程时长
    category_hours = {}
    total_hours = 0

    for sched in schedules:
        # 只统计已完成的日程（或部分完成）
        if sched.status not in ['completed', 'partial']:
            continue

        # 获取时长：优先使用反馈中的实际时长，否则计算日程时长
        actual_h = None
        if sched.id in feedback_dict:
            fb = feedback_dict[sched.id]
            if fb.actual_hours and fb.completion_status in ['已完成', '部分完成']:
                actual_h = fb.actual_hours

        # 如果没有反馈中的实际时长，使用日程时长
        if actual_h is None:
            duration = (datetime.combine(sched.date, sched.end_time) -
                       datetime.combine(sched.date, sched.start_time)).total_seconds() / 3600
            # 如果是休息时间，不计入工作时长
            if not sched.is_break:
                actual_h = duration

        if actual_h:
            category = sched.category or '其他'
            category_hours[category] = category_hours.get(category, 0) + actual_h
            total_hours += actual_h

    summary.total_hours = round(total_hours, 1)
    summary.set_category_stats(category_hours)

    # 构建AI分析数据
    analysis_data = {
        'type': summary_type,
        'period': f"{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}",
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'completion_rate': f"{summary.completion_rate}%",
        'total_hours': f"{total_hours:.1f}",
        'category_breakdown': category_hours,
        'task_details': []
    }

    # 添加任务详情 - 包含有反馈的日程和已完成的日程
    # 使用 no_autoflush 避免懒加载时触发数据库锁定
    with db.session.no_autoflush:
        for sched in schedules:
            # 获取计划时长（直接使用 task_id，避免懒加载）
            planned_h = 0
            try:
                if sched.task_id:
                    # 直接从数据库获取，不通过 ORM 懒加载
                    task = db.session.query(Task).filter_by(id=sched.task_id).first()
                    planned_h = task.estimated_hours if task else 0
            except:
                planned_h = 0

            # 检查是否有反馈
            if sched.id in feedback_dict:
                fb = feedback_dict[sched.id]
                analysis_data['task_details'].append({
                    'title': sched.task_title,
                    'category': sched.category or '其他',
                    'status': fb.completion_status,
                    'planned_hours': planned_h,
                    'actual_hours': fb.actual_hours or 0,
                    'notes': fb.notes
                })
            # 如果没有反馈但日程已完成，也加入统计
            elif sched.status in ['completed', 'partial']:
                duration = (datetime.combine(sched.date, sched.end_time) -
                           datetime.combine(sched.date, sched.start_time)).total_seconds() / 3600
                analysis_data['task_details'].append({
                    'title': sched.task_title,
                    'category': sched.category or '其他',
                    'status': '已完成' if sched.status == 'completed' else '部分完成',
                    'planned_hours': planned_h,
                    'actual_hours': round(duration, 1),
                    'notes': ''
                })

    # 获取每日复盘数据
    reflections = DailyReflection.query.filter(
        DailyReflection.user_id == current_user.id,
        DailyReflection.reflection_date.between(start_date, end_date)
    ).order_by(DailyReflection.reflection_date).all()

    # 构建复盘数据
    reflection_data = []
    for r in reflections:
        reflection_data.append({
            'date': r.reflection_date.strftime('%Y-%m-%d'),
            'core_progress': r.core_progress or '',
            'is_long_term_value': r.is_long_term_value,
            'deep_work_hours': r.deep_work_hours or 0,
            'high_energy_period': r.high_energy_period or '',
            'key_insight': r.key_insight or '',
            'changed_judgment': r.changed_judgment,
            'influences_future': r.influences_future,
            'time_waste': r.time_waste or '',
            'waste_reason': r.waste_reason or '',
            'tomorrow_mit': r.tomorrow_mit or ''
        })

    # AI生成总结和建议
    prompt = f"""请分析以下时间管理数据，生成{title}：

【统计数据】
- 时间范围：{analysis_data['period']}
- 总任务数：{analysis_data['total_tasks']}
- 已完成任务：{analysis_data['completed_tasks']}
- 完成率：{analysis_data['completion_rate']}
- 总工作时长：{analysis_data['total_hours']}小时

【分类统计】
{json.dumps(category_hours, ensure_ascii=False, indent=2)}

【任务详情】
{json.dumps(analysis_data['task_details'], ensure_ascii=False, indent=2)}

【每日复盘数据】
{json.dumps(reflection_data, ensure_ascii=False, indent=2) if reflection_data else '暂无复盘数据'}

请生成一份包含以下内容的总结：
1. **总体评价**：简述这段时间的效率表现
2. **完成情况分析**：分析完成率，找出完成/未完成的原因
3. **每日复盘分析**：结合每日复盘数据，总结：
   - 核心推进成果和长期价值创造
   - 深度工作时长和高能时段规律
   - 关键领悟和认知更新
   - 时间浪费问题及原因分析
   - 明日关键任务(MIT)的执行情况
4. **时间分配建议**：根据分类统计，给出时间分配优化建议
5. **改进措施**：针对发现的问题，结合复盘数据，给出具体可行的改进建议

请用中文输出，条理清晰，语气友好而专业。"""

    ai_response = call_deepseek_api(prompt, max_tokens=2000)

    if ai_response:
        # 尝试分离总结和建议
        if '建议' in ai_response or '改进' in ai_response:
            parts = ai_response.split('建议', 1) if '建议' in ai_response else ai_response.split('改进', 1)
            summary.ai_summary = parts[0]
            summary.ai_suggestions = ('建议' if '建议' in ai_response else '改进') + parts[1] if len(parts) > 1 else ai_response
        else:
            summary.ai_summary = ai_response
            summary.ai_suggestions = ''
    else:
        summary.ai_summary = 'AI生成失败，请检查API配置'
        summary.ai_suggestions = ''

    try:
        db.session.commit()
        flash(f'{title}生成成功', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'生成失败：{str(e)}', 'danger')

    return redirect(url_for('summary.view_summary', summary_id=summary.id))


@summary_bp.route('/<int:summary_id>')
@login_required
def view_summary(summary_id):
    """查看总结详情"""
    summary = Summary.query.filter_by(id=summary_id, user_id=current_user.id).first_or_404()

    # 获取图表数据
    category_stats = summary.get_category_stats()

    return render_template('summary.html', summary=summary, category_stats=category_stats)


@summary_bp.route('/<int:summary_id>/notes', methods=['POST'])
@login_required
def add_notes(summary_id):
    """添加用户心得"""
    summary = Summary.query.filter_by(id=summary_id, user_id=current_user.id).first_or_404()

    notes = request.form.get('notes', '').strip()
    summary.user_notes = notes

    try:
        db.session.commit()
        flash('心得已保存', 'success')
    except Exception as e:
        db.session.rollback()
        flash('保存失败', 'danger')

    return redirect(url_for('summary.view_summary', summary_id=summary_id))


@summary_bp.route('/chart-data')
@login_required
def chart_data():
    """获取图表数据"""
    # 获取参数
    period = request.args.get('period', '30')  # 30, 90, all

    # 确定日期范围
    end_date = datetime.now().date()

    if period == '30':
        start_date = end_date - timedelta(days=30)
    elif period == '90':
        start_date = end_date - timedelta(days=90)
    else:
        start_date = None  # 全部时间

    # 获取已完成的日程（优先使用反馈数据，否则使用日程本身）
    schedules = Schedule.query.filter(
        Schedule.user_id == current_user.id,
        Schedule.status.in_(['completed', 'partial'])
    )

    if start_date:
        schedules = schedules.filter(Schedule.date >= start_date)

    schedules = schedules.all()

    # 获取对应的反馈数据
    schedule_ids = [s.id for s in schedules]
    feedbacks = Feedback.query.filter(
        Feedback.schedule_id.in_(schedule_ids)
    ).all() if schedule_ids else []

    # 构建反馈字典
    feedback_dict = {fb.schedule_id: fb for fb in feedbacks}

    # 按分类统计时长
    category_hours = {}

    for sched in schedules:
        # 获取时长：优先使用反馈中的实际时长，否则计算日程时长
        actual_h = None
        if sched.id in feedback_dict:
            fb = feedback_dict[sched.id]
            if fb.actual_hours and fb.completion_status in ['已完成', '部分完成']:
                actual_h = fb.actual_hours

        # 如果没有反馈中的实际时长，使用日程时长
        if actual_h is None:
            duration = (datetime.combine(sched.date, sched.end_time) -
                       datetime.combine(sched.date, sched.start_time)).total_seconds() / 3600
            # 如果是休息时间，不计入工作时长
            if not sched.is_break:
                actual_h = duration

        if actual_h:
            category = sched.category or '其他'
            category_hours[category] = category_hours.get(category, 0) + actual_h

    # 构建图表数据
    labels = list(category_hours.keys())
    data = [round(h, 1) for h in category_hours.values()]

    return jsonify({
        'labels': labels,
        'data': data
    })
