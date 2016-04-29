import json
import os
import pkg_resources
import zipfile
import shutil

from django.conf import settings
from webob import Response

from xblock.core import XBlock
from xblock.fields import Scope, String, Integer
from xblock.fragment import Fragment

from mako.template import Template as MakoTemplate


# Make '_' a no-op so we can scrape strings
_ = lambda text: text


SCORM_PKG_INTERNAL = ('SCORM_PKG_INTERNAL', 'index.html in SCORM package')


DEFINED_PLAYERS = getattr(settings, "SCORM_PLAYER_BACKENDS", [])


class ScormXBlock(XBlock):

    has_score = True

    display_name = String(
        display_name=_("Display Name"),
        help=_("Display name for this module"),
        default="Scorm",
        scope=Scope.settings
    )
    scorm_file = String(
        display_name=_("Upload scorm file"),
        scope=Scope.settings
    )
    scorm_player = String(
        values=[player['name'] for  player in DEFINED_PLAYERS] + [SCORM_PKG_INTERNAL, ],
        display_name=_("SCORM player"),
        help=_("SCORM player configured in Django settings, or index.html file contained in SCORM package"),
        scope=Scope.settings
    )
    lesson_status = String(
        scope=Scope.user_state,
        default='not attempted'
    )
    lesson_score = Integer(
        scope=Scope.user_state,
        default=0
    )
    weight = Integer(
        default=1,
        scope=Scope.settings
    )
    display_type = String(
        display_name =_("Display Type"),
        values=["iframe", "popup"],
        default="iframe",
        help=_("Open in a new popup window, or an iframe.  This setting may be overridden by player-specific configuration."),
        scope=Scope.settings
    )
    display_width = Integer(
        default=820,
        scope=Scope.settings
    )
    display_height = Integer(
        default=450,
        scope=Scope.settings
    )

    def resource_string(self, path):
        """Handy helper for getting resources from our kit."""
        data = pkg_resources.resource_string(__name__, path)
        return data.decode("utf8")

    def student_view(self, context=None):
        scheme = 'https' if settings.HTTPS == 'on' else 'http'
        scorm_file = '{}://{}{}'.format(scheme, settings.ENV_TOKENS.get('LMS_BASE'), self.scorm_file)
        html = self.resource_string("static/html/scormxblock.html")
        frag = Fragment(html.format(scorm_file=scorm_file, self=self))
        frag.add_css(self.resource_string("static/css/scormxblock.css"))
        frag.add_javascript(self.resource_string("static/js/src/scormxblock.js"))
        frag.initialize_js('ScormXBlock')
        return frag

    def studio_view(self, context=None):
        html = self.resource_string("static/html/studio.html")
        frag = Fragment()
        context = {'block': self}
        frag.add_content(MakoTemplate(text=html).render_unicode(**context))
        frag.add_css(self.resource_string("static/css/scormxblock.css"))
        frag.add_javascript(self.resource_string("static/js/src/studio.js"))
        frag.initialize_js('ScormStudioXBlock')
        return frag

    @XBlock.handler
    def studio_submit(self, request, suffix=''):
        self.display_name = request.params['display_name']
        self.weight = request.params['weight']
        self.display_width = request.params['display_width']
        self.display_height = request.params['display_height']
        self.display_type = request.params['display_type']
        self.scorm_player = request.params['scorm_player']

        # TODO: save the file according to DEFAULT_FILE_STORAGE setting
        # scorm_file should only point to the path where imsmanifest.xml is located
        # scorm_player will have the index.html, launch.htm location for the JS player
        if hasattr(request.params['file'], 'file'):
            file = request.params['file'].file
            zip_file = zipfile.ZipFile(file, 'r')
            path_to_file = os.path.join(settings.PROFILE_IMAGE_BACKEND['options']['location'], self.location.block_id)
            if os.path.exists(path_to_file):
                shutil.rmtree(path_to_file)
            zip_file.extractall(path_to_file)
            self.scorm_file = os.path.join(settings.PROFILE_IMAGE_BACKEND['options']['base_url'],
                                           '{}/index.html'.format(self.location.block_id))

        return Response(json.dumps({'result': 'success'}), content_type='application/json')

    @XBlock.json_handler
    def scorm_get_value(self, data, suffix=''):
        name = data.get('name')
        if name == 'cmi.core.lesson_status':
            return {'value': self.lesson_status}
        return {'value': ''}

    @XBlock.json_handler
    def scorm_set_value(self, data, suffix=''):
        context = {'result': 'success'}
        name = data.get('name')
        if name == 'cmi.core.lesson_status' and data.get('value') != 'completed':
            self.lesson_status = data.get('value')
            self.publish_grade()
            context.update({"lesson_score": self.lesson_score})
        if name == 'cmi.core.score.raw':
            self.lesson_score = int(data.get('value', 0))/100.0
        return context

    def publish_grade(self):
        if self.lesson_status == 'passed':
            self.runtime.publish(
                self,
                'grade',
                {
                    'value': self.lesson_score,
                    'max_value': self.weight,
                })
        if self.lesson_status == 'failed':
            self.runtime.publish(
                self,
                'grade',
                {
                    'value': 0,
                    'max_value': self.weight,
                })
            self.lesson_score = 0

    @staticmethod
    def workbench_scenarios():
        """A canned scenario for display in the workbench."""
        return [
            ("ScormXBlock",
             """<vertical_demo>
                <scormxblock/>
                </vertical_demo>
             """),
        ]
