import json
import os
import pkg_resources
import zipfile
import shutil
import tempfile

from django.conf import settings
from django.core.files.storage import default_storage
from webob import Response

from xblock.core import XBlock
from xblock.fields import Scope, String, Integer
from xblock.fragment import Fragment

from mako.template import Template as MakoTemplate


# Make '_' a no-op so we can scrape strings
_ = lambda text: text


SCORM_PKG_INTERNAL = {"value": "SCORM_PKG_INTERNAL", "display_name": "Internal Player: index.html in SCORM package"}


DEFINED_PLAYERS = settings.ENV_TOKENS.get("SCORM_PLAYER_BACKENDS", {})



class ScormXBlock(XBlock):

    has_score = True

    display_name = String(
        display_name=_("Display Name"),
        help=_("Display name for this module"),
        default="Scorm",
        scope=Scope.settings
    )
    description = String(
        display_name=_("Description"),
        help=_("Brief description of the SCORM modules will be displayed above the player. Can contain HTML."),
        default="",
        scope=Scope.settings
    )
    scorm_file = String(
        display_name=_("Upload scorm file (.zip)"),
        help=_('Upload a new SCORM package.'),
        scope=Scope.settings
    )
    scorm_player = String(
        values=[{"value": key, "display_name": DEFINED_PLAYERS[key]['name']} for key in DEFINED_PLAYERS.keys()] + [SCORM_PKG_INTERNAL, ],
        display_name=_("SCORM player"),
        help=_("SCORM player configured in Django settings, or index.html file contained in SCORM package"),
        scope=Scope.settings
    )
    # this stores latest raw SCORM API data in JSON string
    raw_scorm_status = String(
        scope=Scope.user_state,
        default='{}'
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
        help=_('Point weight of SCORM module in course'),
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
        display_name =_("Display Width (px)"),
        help=_('Width of iframe or popup window'),
        default=820,
        scope=Scope.settings
    )
    display_height = Integer(
        display_name =_("Display Height (px)"),
        help=_('Height of iframe or popup window'),
        default=450,
        scope=Scope.settings
    )
    player_configuration = String(
        display_name =_("Player Configuration"),
        default='',
        help=_("JSON object string with overrides to be passed to selected SCORM player.  These will be exposed as data attributes on the host iframe and sent in a window.postMessage to the iframe's content window. Attributes can be any.  'Internal player' will always check this field for an 'initial_html' attribute to override index.html as the initial page."),
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
        if hasattr(self, "xmodule_runtime"):
            user = self.xmodule_runtime._services['user'].get_current_user()
            return user.full_name
        else:
            return None

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
        scorm_player_url = ""

        if self.scorm_player == 'SCORM_PKG_INTERNAL':
            # TODO: support initial filename other than index.html for internal players
            scorm_player_url = '{}://{}{}'.format(scheme, lms_base, self.scorm_file)
        elif self.scorm_player:
            # SSLA: launch.htm?courseId=1&studentName=Caudill,Brian&studentId=1&courseDirectory=courses/SSLA_tryout
            player_config = DEFINED_PLAYERS[self.scorm_player]
            player  = player_config['location']
            if '://' in player:
                scorm_player_url = player
            else:    
                scorm_player_url = '{}://{}{}'.format(scheme, lms_base, player)
                    
        html = self.resource_string("static/html/scormxblock.html")

        # don't call handlers if student_view is not called from within LMS
        # (not really a student)
        if self.runtime.HOSTNAME:
            get_url = self.runtime.handler_url(self, "get_raw_scorm_status")
            set_url = self.runtime.handler_url(self, "set_raw_scorm_status")
        # PreviewModuleSystem (runtime Mixin from Studio) won't have a hostname            
        else:
            # we don't want to get/set SCORM status from preview
            get_url = set_url = '#'


        # if display type is popup, don't use the full window width for the host iframe
        iframe_width = self.display_type=='popup' and 800 or self.display_width;
        iframe_height = self.display_type=='popup' and 400 or self.display_height;

        try:
            player_config = json.loads(self.player_configuration)
        except ValueError:
            player_config = {}

        frag = Fragment()
        frag.add_content(MakoTemplate(text=html.format(self=self, scorm_player_url=scorm_player_url,
                                                       get_url=get_url, set_url=set_url, 
                                                       iframe_width=iframe_width, iframe_height=iframe_height,
                                                       player_config=player_config, 
                                                       scorm_file=self.scorm_file)
                                     ).render_unicode())
        frag.add_css(self.resource_string("static/css/scormxblock.css"))
        js = self.resource_string("static/js/src/scormxblock.js")
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
        self.description = request.params['description']
        self.weight = request.params['weight']
        self.display_width = request.params['display_width']
        self.display_height = request.params['display_height']
        self.display_type = request.params['display_type']
        self.scorm_player = request.params['scorm_player']

        try:
            json.loads(request.params['player_configuration'])  # just validation
            self.player_configuration = request.params['player_configuration']
        except ValueError, e:
            return Response(json.dumps({'result': 'failure', 'error': 'Invalid JSON in Player Configuration'.format(e)}), content_type='application/json')

        # scorm_file should only point to the path where imsmanifest.xml is located
        # scorm_player will have the index.html, launch.htm, etc. location for the JS player
        # TODO: the below could fail after deleting all of the contents from the storage. to handle
        if hasattr(request.params['file'], 'file'):
            file = request.params['file'].file
            zip_file = zipfile.ZipFile(file, 'r')
            storage = default_storage

            scorm_storage = settings.ENV_TOKENS.get("SCORM_PKG_STORAGE_DIR", "scormpackages")
            path_to_file = os.path.join(scorm_storage, self.location.block_id)

            if storage.exists(os.path.join(path_to_file, 'imsmanifest.xml')):
                try:
                    shutil.rmtree(os.path.join(storage.location, path_to_file))
                except OSError:
                    # TODO: for now we are going to assume this means it's stored on S3 if not local
                    try:
                        for key in storage.bucket.list(prefix=path_to_file):
                            key.delete()
                    except AttributeError:
                        return Response(json.dumps({'result': 'failure', 'error': 'Unsupported storage. Unable to overwrite old SCORM package contents'}), content_type='application/json')

            tempdir = tempfile.mkdtemp()
            zip_file.extractall(tempdir)

            to_store = []
            for (dirpath, dirnames, files) in os.walk(tempdir):
                for f in files:
                    to_store.append(os.path.join(os.path.abspath(dirpath), f))

            # TODO: look at optimization of file handling, save
            for f in to_store:
                f_path = f.replace(tempdir, '')
                with open(f, 'rb+') as fh:
                    storage.save('{}{}'.format(path_to_file, f_path), fh)
            shutil.rmtree(tempdir)

            # strip querystrings
            url = storage.url(path_to_file)
            self.scorm_file = url[:url.find('?')]
        import pdb; pdb.set_trace()

        return Response(json.dumps({'result': 'success'}), content_type='application/json')

    # if player sends SCORM API JSON directly
    @XBlock.json_handler
    def scorm_get_value(self, data, suffix=''):
        name = data.get('name')
        if name == 'cmi.core.lesson_status':
            return {'value': self.lesson_status}
        return {'value': ''}

    # if player sends SCORM API JSON directly
    @XBlock.json_handler
    def scorm_set_value(self, data, suffix=''):
        context = {'result': 'success'}
        name = data.get('name')
        if name == 'cmi.core.lesson_status' and data.get('value') != 'completed':
            self.lesson_status = data.get('value')
            self.publish_grade()
            context.update({"lesson_score": self.lesson_score})
        if name == 'cmi.core.score.raw':
            self.set_lesson_score(data.get('value',0))
        return context

    # if player POSTS form data including SCORM API JSON data
    @XBlock.handler
    def get_raw_scorm_status(self, request, suffix=''):

        # TODO: handle errors
        return Response(self.raw_scorm_status, content_type='application/json')

    # if player POSTS form data including SCORM API JSON data
    @XBlock.handler
    def set_raw_scorm_status(self, request, suffix=''):
        data = request.POST['data']
        self.raw_scorm_status = data
        scorm_data = json.loads(data)
        status = scorm_data.get('cmi.core.lesson_status', 'incomplete')
        if status != 'completed':
            self.lesson_status = status
        self.set_lesson_score(scorm_data.get('cmi.core.score.raw', 0))
        self.publish_grade()
        
        # TODO: handle errors
        return Response(json.dumps({'result': 'success'}), content_type='application/json')

    def set_lesson_score(self, scorm_score):
        self.lesson_score = int(scorm_score)/100.0

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
