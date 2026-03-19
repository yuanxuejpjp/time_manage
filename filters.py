from datetime import datetime
from jinja2 import Environment

def get_icon_for_date_type(date_type):
    """获取日期类型对应的Bootstrap图标类名"""
    icon_map = {
        'birthday': 'cake2',
        'anniversary': 'heart',
        'deadline': 'clock',
        'holiday': 'star',
        'other': 'calendar'
    }
    return icon_map.get(date_type, 'calendar')


def register_filters(app):
    """注册自定义过滤器"""

    # 注册为全局函数，可在模板中直接调用
    app.jinja_env.globals['get_icon_for_date_type'] = get_icon_for_date_type

    @app.template_filter('date_filter')
    def date_filter(date_val):
        """格式化日期为 YYYY-MM-DD"""
        if date_val:
            if isinstance(date_val, datetime):
                return date_val.strftime('%Y-%m-%d')
            return str(date_val)
        return ''

    @app.template_filter('date_filter_long')
    def date_filter_long(date_val):
        """格式化日期为中文长格式"""
        if date_val:
            # 如果是字符串，先转换为 date 对象
            if isinstance(date_val, str):
                from datetime import datetime as dt
                date_val = dt.strptime(date_val, '%Y-%m-%d').date()

            weekdays = ['一', '二', '三', '四', '五', '六', '日']
            weekday = weekdays[date_val.weekday()]
            if isinstance(date_val, datetime):
                date_str = date_val.strftime('%Y年%m月%d日')
            else:
                date_str = date_val.strftime('%Y年%m月%d日')
            return f'{date_str} 星期{weekday}'
        return ''

    @app.template_filter('time_filter')
    def time_filter(time_val):
        """格式化时间为 HH:MM"""
        if time_val:
            return time_val.strftime('%H:%M')
        return ''

    @app.template_filter('datetime_filter')
    def datetime_filter(datetime_val):
        """格式化日期时间为 YYYY-MM-DD HH:MM"""
        if datetime_val:
            return datetime_val.strftime('%Y-%m-%d %H:%M')
        return ''

    @app.template_filter('datetime_local_filter')
    def datetime_local_filter(datetime_val):
        """格式化为 datetime-local 输入格式"""
        if datetime_val:
            return datetime_val.strftime('%Y-%m-%dT%H:%M')
        return ''

    @app.template_filter('today_str')
    def today_str(date_val):
        """格式化今天日期为中文"""
        if date_val:
            if isinstance(date_val, datetime):
                date_val = date_val.date()
            weekdays = ['一', '二', '三', '四', '五', '六', '日']
            weekday = weekdays[date_val.weekday()]
            return date_val.strftime(f'%Y年%m月%d日 星期{weekday}')
        return ''

    @app.template_filter('status_filter')
    def status_filter(status):
        """状态中文转换"""
        status_map = {
            'pending': '待完成',
            'completed': '已完成',
            'partial': '部分完成',
            'cancelled': '已取消',
            'scheduled': '已安排'
        }
        return status_map.get(status, status)

    @app.template_filter('status_class')
    def status_class(status):
        """状态对应的CSS类"""
        status_map = {
            'pending': 'pending',
            'completed': 'completed',
            'partial': 'partial',
            'cancelled': 'cancelled',
            'scheduled': 'scheduled'
        }
        return status_map.get(status, 'pending')

    @app.template_filter('priority_class')
    def priority_class(priority):
        """优先级对应的CSS类"""
        priority_map = {
            '高': 'high',
            '中': 'medium',
            '低': 'low'
        }
        return priority_map.get(priority, 'medium')

    @app.template_filter('summary_type_filter')
    def summary_type_filter(summary_type):
        """总结类型中文转换"""
        type_map = {
            'daily': '日报',
            'weekly': '周报',
            'monthly': '月报'
        }
        return type_map.get(summary_type, summary_type)

    @app.template_filter('recurring_type_filter')
    def recurring_type_filter(recurring_type):
        """重复类型中文转换"""
        type_map = {
            'daily': '每天',
            'weekly': '每周',
            'weekly_days': '每周指定天'
        }
        return type_map.get(recurring_type, recurring_type)

    @app.template_filter('frequency_filter')
    def frequency_filter(frequency):
        """习惯频率中文转换"""
        type_map = {
            'daily': '每天',
            'weekdays': '工作日',
            'weekends': '周末',
            'weekly': '每周指定天'
        }
        return type_map.get(frequency, frequency)

    @app.template_filter('date_type_filter')
    def date_type_filter(date_type):
        """日期类型中文转换和图标"""
        type_map = {
            'birthday': '🎂 生日',
            'anniversary': '💝 纪念日',
            'deadline': '📅 截止日期',
            'holiday': '🎉 节日',
            'other': '📌 其他'
        }
        return type_map.get(date_type, date_type)
