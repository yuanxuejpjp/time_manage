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

    print(f'[DEBUG] API Key configured: {bool(api_key)}')
    print(f'[DEBUG] API Key length: {len(api_key) if api_key else 0}')
    print(f'[DEBUG] Base URL: {base_url}')

    if not api_key:
        print('[ERROR] DeepSeek API key not configured')
        return None

    try:
        # 禁用代理，避免系统代理干扰
        session = requests.Session()
        session.trust_env = False  # 忽略系统代理设置

        print(f'[DEBUG] Sending request to DeepSeek API...')
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
            timeout=90,  # 增加超时时间到90秒
            verify=True
        )

        print(f'[DEBUG] Response status: {response.status_code}')

        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            print(f'[DEBUG] API response received, length: {len(content)}')
            return content
        else:
            print(f'[ERROR] DeepSeek API error: {response.status_code} - {response.text}')
            return None

    except requests.exceptions.ProxyError as e:
        print(f'[ERROR] DeepSeek API proxy error: {str(e)}')
        print('提示：请检查系统代理设置或尝试关闭代理')
        return None
    except requests.exceptions.SSLError as e:
        print(f'[ERROR] DeepSeek API SSL error: {str(e)}')
        print('提示：SSL连接失败，可能需要配置VPN或检查网络')
        return None
    except requests.exceptions.Timeout as e:
        print(f'[ERROR] DeepSeek API timeout: {str(e)}')
        print('提示：连接超时，请检查网络或稍后重试')
        return None
    except Exception as e:
        print(f'[ERROR] DeepSeek API exception: {type(e).__name__}: {str(e)}')
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
    total_deep_work_hours = 0
    long_term_value_count = 0
    changed_judgment_count = 0
    time_waste_list = []
    key_insights = []
    mit_list = []

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

        # 统计复盘数据
        if r.deep_work_hours:
            total_deep_work_hours += r.deep_work_hours
        if r.is_long_term_value:
            long_term_value_count += 1
        if r.changed_judgment:
            changed_judgment_count += 1
        if r.time_waste:
            time_waste_list.append({
                'date': r.reflection_date.strftime('%m-%d'),
                'waste': r.time_waste,
                'reason': r.waste_reason or ''
            })
        if r.key_insight:
            key_insights.append({
                'date': r.reflection_date.strftime('%m-%d'),
                'insight': r.key_insight
            })
        if r.tomorrow_mit:
            mit_list.append({
                'date': r.reflection_date.strftime('%m-%d'),
                'mit': r.tomorrow_mit
            })

    # 计算复盘统计
    reflection_stats = {
        'total_days': len(reflections),
        'total_deep_work_hours': round(total_deep_work_hours, 1),
        'avg_deep_work_hours': round(total_deep_work_hours / len(reflections), 1) if reflections else 0,
        'long_term_value_ratio': round(long_term_value_count / len(reflections) * 100, 1) if reflections else 0,
        'changed_judgment_count': changed_judgment_count,
        'has_insights': len(key_insights) > 0,
        'has_waste': len(time_waste_list) > 0
    }

    # 如果没有复盘数据，提示用户
    if not reflections:
        summary.ai_summary = f'暂无{title}的每日复盘数据。请先在"每日复盘"中记录这段时间的复盘内容，再生成报告。'
        summary.ai_suggestions = '💡 建议每天花5-10分钟进行复盘，记录：\n1. 今日核心推进\n2. 深度工作时间\n3. 关键领悟\n4. 时间浪费分析\n5. 明日关键任务'
        db.session.commit()
        flash(f'{title}生成失败：暂无复盘数据', 'warning')
        return redirect(url_for('summary.view_summary', summary_id=summary.id))

    # 直接生成总结和建议 - 不调用AI，直接拼接复盘数据
    print(f"[DEBUG] 开始生成{title}（直接拼接复盘数据）...")

    # 构建总结内容
    summary_parts = []

    # 总体评价
    summary_parts.append(f"""## 📊 总体评价

**时间范围**：{analysis_data['period']}
**复盘天数**：{reflection_stats['total_days']}天
**深度工作**：总时长{reflection_stats['total_deep_work_hours']}小时，平均每日{reflection_stats['avg_deep_work_hours']}小时
**长期价值**：{long_term_value_count}天产生长期价值，占比{reflection_stats['long_term_value_ratio']}%
**认知更新**：改变判断{changed_judgment_count}次""")

    # 核心推进
    core_progress_list = []
    for r in reflection_data:
        if r.get('core_progress'):
            value_tag = ' 🌟' if r.get('is_long_term_value') else ''
            core_progress_list.append(f"- **{r['date']}**{value_tag}：{r['core_progress']}")

    if core_progress_list:
        summary_parts.append(f"""

## 🎯 核心推进

{chr(10).join(core_progress_list)}""")
    else:
        summary_parts.append(f"""

## 🎯 核心推进

暂无核心推进记录""")

    # 深度工作分析
    summary_parts.append(f"""

## ⏰ 深度工作分析

- **总时长**：{reflection_stats['total_deep_work_hours']}小时
- **平均每日**：{reflection_stats['avg_deep_work_hours']}小时""")

    # 关键领悟
    if key_insights:
        insight_list = [f"- **{i['date']}**：{i['insight']}" for i in key_insights]
        summary_parts.append(f"""

## 💡 关键领悟

{chr(10).join(insight_list)}""")
    else:
        summary_parts.append(f"""

## 💡 关键领悟

暂无关键领悟记录""")

    # 时间浪费
    if time_waste_list:
        waste_list = [f"- **{w['date']}**：{w['waste']}" + (f"（原因：{w['reason']}）" if w.get('reason') else '') for w in time_waste_list]
        summary_parts.append(f"""

## ⚠️ 时间浪费分析

{chr(10).join(waste_list)}""")
    else:
        summary_parts.append(f"""

## ⚠️ 时间浪费分析

🎉 很棒！这段时间没有记录时间浪费""")

    # MIT执行回顾
    if mit_list:
        mit_summary = [f"- **{m['date']}**：{m['mit']}" for m in mit_list]
        summary_parts.append(f"""

## 📋 明日关键任务(MIT)回顾

{chr(10).join(mit_summary)}""")
    else:
        summary_parts.append(f"""

## 📋 明日关键任务(MIT)回顾

暂无MIT记录""")

    # 组合总结
    summary.ai_summary = ''.join(summary_parts)

    # 生成改进建议
    suggestions = []

    # 深度工作建议
    if reflection_stats['avg_deep_work_hours'] < 2:
        suggestions.append("💡 **提升深度工作**：当前平均每日深度工作不足2小时，建议逐步增加深度工作时间，关闭手机通知，专注重要任务。")
    elif reflection_stats['avg_deep_work_hours'] >= 4:
        suggestions.append("👍 **保持深度工作**：深度工作时长很不错，继续保持专注状态！")

    # 长期价值建议
    if reflection_stats['long_term_value_ratio'] < 50:
        suggestions.append("🎯 **聚焦长期价值**：建议在做任务时多思考：这件事一年后还有价值吗？优先做重要不紧急的事。")
    else:
        suggestions.append("🌟 **长期价值导向**：很好！大部分时间都在创造长期价值，继续保持。")

    # 时间浪费建议
    if time_waste_list:
        waste_types = [w['waste'] for w in time_waste_list]
        if '刷手机' in str(waste_types) or '抖音' in str(waste_types) or '游戏' in str(waste_types):
            suggestions.append("📱 **减少数字沉迷**：建议设置使用时间限制，用番茄工作法保持专注。")

    # 认知更新建议
    if changed_judgment_count == 0:
        suggestions.append("🧠 **保持开放思维**：尝试接触新观点，勇于挑战和更新自己的判断。")

    if not suggestions:
        suggestions = ["🎉 继续保持良好的时间管理习惯，每天进步一点点！"]

    summary.ai_suggestions = '\n\n'.join(suggestions)

    print(f"[DEBUG] {title}生成完成")

    try:
        db.session.commit()
        flash(f'{title}生成成功', 'success')
    except Exception as e:
        print(f"[DEBUG] 数据库提交失败: {str(e)}")
        db.session.rollback()
        flash(f'保存失败：{str(e)}', 'danger')

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
