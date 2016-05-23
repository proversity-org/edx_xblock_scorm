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


SCORM_PKG_INTERNAL = {"value": "SCORM_PKG_INTERNAL", "display_name": "index.html in SCORM package"}


DEFINED_PLAYERS = settings.ENV_TOKENS.get("SCORM_PLAYER_BACKENDS", {})



class ScormXBlock(XBlock):

    has_score = True

    display_name = String(
        display_name=_("Display Name"),
        help=_("Display name for this module"),
        default="Scorm",
        scope=Scope.settings
    )
    scorm_file = String(
        display_name=_("Upload scorm file (.zip)"),
        scope=Scope.settings
    )
    scorm_player = String(
        values=[{"value": key, "display_name": DEFINED_PLAYERS[key]['name']} for key in DEFINED_PLAYERS.keys()] + [SCORM_PKG_INTERNAL, ],
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

    @property
    def student_id(self):
        if hasattr(self, "scope_ids"):
            return self.scope_ids.user_id
        else:
            return None

    @property
    def student_name(self):
        # TODO: dummy 
        return "Wilson,Bryan"

    @property
    def course_id(self):
        if hasattr(self, "xmodule_runtime"):
            return self._serialize_opaque_key(self.xmodule_runtime.course_id)
        else:
            return None

    def _serialize_opaque_key(self, key):
        if hasattr(key, 'to_deprecated_string'):
            return key.to_deprecated_string()
        else:
            return unicode(key)        

    def resource_string(self, path):
        """Handy helper for getting resources from our kit."""
        data = pkg_resources.resource_string(__name__, path)
        return data.decode("utf8")

    def student_view(self, context=None):
        scheme = 'https' if settings.HTTPS == 'on' else 'http'
        lms_base = settings.ENV_TOKENS.get('LMS_BASE')
        scorm_file = '{}://{}{}'.format(scheme, lms_base, self.scorm_file)
        scorm_player_url = ""

        if self.scorm_player == SCORM_PKG_INTERNAL:
            scorm_player_url = '{0}/index.html'.format(scorm_file) 
        elif self.scorm_player:
            # SSLA: launch.htm?courseId=1&studentName=Caudill,Brian&studentId=1&courseDirectory=courses/SSLA_tryout
            
            player_config = DEFINED_PLAYERS[self.scorm_player]
            scorm_player_url_base = '{}://{}{}'.format(scheme, settings.ENV_TOKENS.get('LMS_BASE'), player_config['location'])
            
            # TODO: temp dummy. specific to SSLA
            # TODO: define querystring to player in the player "configuration" key
            scorm_player_url_query = ('courseId={course_id}&' 
                                      'studentName={student_name}&'
                                      'studentId={student_id}&'
                                      'courseDirectory={course_directory}'
                                      ).format(
                                      course_id=self.course_id,
                                      student_name=self.student_name,
                                      student_id=self.student_id,
                                      course_directory=self.scorm_file)
            scorm_player_url = '{0}?{1}'.format(scorm_player_url_base, scorm_player_url_query)
        
        html = self.resource_string("static/html/scormxblock.html")

        # don't call handlers if student_view is not called from within LMS
        # (not really a student)
        if self.runtime.HOSTNAME:
            get_url = self.runtime.handler_url(self, "scorm_get_value")
            set_url = self.runtime.handler_url(self, "scorm_set_value")
        # PreviewModuleSystem (runtime Mixin from Studio) won't have a hostname            
        else:
            # preview from Studio may have cross-frame-origin problems so we don't want it 
            # trying to access any URL
            get_url = set_url = 'javascript:void(0)'

        frag = Fragment(html.format(self=self, scorm_file=scorm_file, scorm_player_url=scorm_player_url))
        frag.add_css(self.resource_string("static/css/scormxblock.css"))
        js = self.resource_string("static/js/src/scormxblock.js") % (get_url, set_url)
        frag.add_javascript(js)
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
        # scorm_player will have the index.html, launch.htm, etc. location for the JS player
        if hasattr(request.params['file'], 'file'):
            file = request.params['file'].file
            zip_file = zipfile.ZipFile(file, 'r')
            path_to_file = os.path.join(settings.PROFILE_IMAGE_BACKEND['options']['location'], self.location.block_id)
            if os.path.exists(path_to_file):
                shutil.rmtree(path_to_file)
            zip_file.extractall(path_to_file)
            self.scorm_file = os.path.join(settings.PROFILE_IMAGE_BACKEND['options']['base_url'],
                                           '{}'.format(self.location.block_id))

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
