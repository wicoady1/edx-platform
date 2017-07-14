"""
Views for the course home page.
"""

from django.core.context_processors import csrf
from django.core.urlresolvers import reverse
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import ensure_csrf_cookie

from courseware.access import has_access
from courseware.courses import (
    can_self_enroll_in_course,
    get_course_info_section,
    get_course_with_access,
)
from lms.djangoapps.courseware.exceptions import CourseAccessRedirect
from lms.djangoapps.courseware.views.views import CourseTabView
from opaque_keys.edx.keys import CourseKey
from openedx.core.djangoapps.plugin_api.views import EdxFragmentView
from openedx.features.course_experience.course_tools import CourseToolsPluginManager
from student.models import CourseEnrollment
from util.views import ensure_valid_course_key
from web_fragments.fragment import Fragment

from ..utils import get_course_outline_block_tree
from .course_dates import CourseDatesFragmentView
from .course_outline import CourseOutlineFragmentView
from .course_sock import CourseSockFragmentView
from .welcome_message import WelcomeMessageFragmentView

EMPTY_HANDOUTS_HTML = u'<ol></ol>'


class CourseHomeView(CourseTabView):
    """
    The home page for a course.
    """
    @method_decorator(ensure_csrf_cookie)
    @method_decorator(cache_control(no_cache=True, no_store=True, must_revalidate=True))
    @method_decorator(ensure_valid_course_key)
    def get(self, request, course_id, **kwargs):
        """
        Displays the home page for the specified course.
        """
        return super(CourseHomeView, self).get(request, course_id, 'courseware', **kwargs)

    def render_to_fragment(self, request, course=None, tab=None, **kwargs):
        course_id = unicode(course.id)
        home_fragment_view = CourseHomeFragmentView()
        return home_fragment_view.render_to_fragment(request, course_id=course_id, **kwargs)


class CourseHomeFragmentView(EdxFragmentView):
    """
    A fragment to render the home page for a course.
    """

    def _get_resume_course_info(self, request, course_id):
        """
        Returns information relevant to resume course functionality.

        Returns a tuple: (has_visited_course, resume_course_url)
            has_visited_course: True if the user has ever visted the course, False otherwise.
            resume_course_url: The URL of the last accessed block if the user has visited the course,
                otherwise the URL of the course root.

        """

        def get_last_accessed_block(block):
            """
            Gets the deepest block marked as 'last_accessed'.
            """
            if not block['last_accessed']:
                return None
            if not block.get('children'):
                return block
            for child in block['children']:
                last_accessed_block = get_last_accessed_block(child)
                if last_accessed_block:
                    return last_accessed_block
            return block

        course_outline_root_block = get_course_outline_block_tree(request, course_id)
        last_accessed_block = get_last_accessed_block(course_outline_root_block) if course_outline_root_block else None
        has_visited_course = bool(last_accessed_block)
        if last_accessed_block:
            resume_course_url = last_accessed_block['lms_web_url']
        else:
            resume_course_url = course_outline_root_block['lms_web_url'] if course_outline_root_block else None

        return has_visited_course, resume_course_url

    def _get_course_handouts(self, request, course):
        """
        Returns the handouts for the specified course.
        """
        handouts = get_course_info_section(request, request.user, course, 'handouts')
        if not handouts or handouts == EMPTY_HANDOUTS_HTML:
            return None
        return handouts

    def render_to_fragment(self, request, course_id=None, **kwargs):
        """
        Renders the course's home page as a fragment.
        """
        course_key = CourseKey.from_string(course_id)
        course = get_course_with_access(request.user, 'load', course_key)

        # Render the course dates as a fragment
        dates_fragment = CourseDatesFragmentView().render_to_fragment(request, course_id=course_id, **kwargs)

        # Render the full content to enrolled users, as well as to course and global staff.
        # Unenrolled users who are not course or global staff are given only a subset.
        is_enrolled = CourseEnrollment.is_enrolled(request.user, course_key)
        is_staff = has_access(request.user, 'staff', course_key)
        if is_enrolled or is_staff:
            outline_fragment = CourseOutlineFragmentView().render_to_fragment(request, course_id=course_id, **kwargs)
            welcome_message_fragment = WelcomeMessageFragmentView().render_to_fragment(
                request, course_id=course_id, **kwargs
            )
            course_sock_fragment = CourseSockFragmentView().render_to_fragment(request, course=course, **kwargs)
            has_visited_course, resume_course_url = self._get_resume_course_info(request, course_id)
        else:
            # Redirect the user to the dashboard if they are not enrolled and
            # this is a course that does not support direct enrollment.
            if not can_self_enroll_in_course(course_key):
                raise CourseAccessRedirect(reverse('dashboard'))

            # Set all the fragments
            outline_fragment = None
            welcome_message_fragment = None
            course_sock_fragment = None
            has_visited_course = None
            resume_course_url = None

        # Get the handouts
        handouts_html = self._get_course_handouts(request, course)

        # Get the course tools enabled for this user and course
        course_tools = CourseToolsPluginManager.get_enabled_course_tools(request, course_key)

        # Render the course home fragment
        context = {
            'request': request,
            'csrf': csrf(request)['csrf_token'],
            'course': course,
            'course_key': course_key,
            'outline_fragment': outline_fragment,
            'handouts_html': handouts_html,
            'has_visited_course': has_visited_course,
            'resume_course_url': resume_course_url,
            'course_tools': course_tools,
            'dates_fragment': dates_fragment,
            'welcome_message_fragment': welcome_message_fragment,
            'course_sock_fragment': course_sock_fragment,
            'disable_courseware_js': True,
            'uses_pattern_library': True,
        }
        html = render_to_string('course_experience/course-home-fragment.html', context)
        return Fragment(html)
