# -*- coding: utf-8 -*-
#

# Imports ###########################################################

import logging
import json
import webob
import copy
import urllib

from xblock.core import XBlock
from xblock.fields import Scope, String, Dict, Float, Boolean
from xblock.fragment import Fragment

from .utils import render_template, load_resource
from .default_data import default_data


# Globals ###########################################################

log = logging.getLogger(__name__)


# Classes ###########################################################

class DragAndDropBlock(XBlock):
    """
    XBlock providing a Drag and Drop question
    """
    display_name = String(
        display_name="Title",
        help="The title of the Drag and Drop that is displayed to the user",
        scope=Scope.settings,
        default="Drag and Drop"
    )

    question_text = String(
        display_name="Question text",
        help="The question text that is displayed to the user",
        scope=Scope.settings,
        default=""
    )

    weight = Float(
        display_name="Weight",
        help="This is the maximum score that the user receives when he/she successfully completes the problem",
        scope=Scope.settings,
        default=1
    )

    data = Dict(
        display_name="Drag and Drop",
        help="JSON spec as generated by the builder",
        scope=Scope.content,
        default=default_data
    )

    item_state = Dict(
        help="How the student has interacted with the problem",
        scope=Scope.user_state,
        default={}
    )

    completed = Boolean(
        help="The student has completed the problem at least once",
        scope=Scope.user_state,
        default=False
    )

    has_score = True

    def student_view(self, context):
        """
        Player view, displayed to the student
        """

        js_templates = load_resource('/templates/html/js_templates.html')

        context = {
            'js_templates': js_templates,
            'title': self.display_name,
            'question_text': self.question_text,
        }

        fragment = Fragment()
        fragment.add_content(render_template('/templates/html/drag_and_drop.html', context))
        fragment.add_css_url(self.runtime.local_resource_url(self,
            'public/css/vendor/jquery-ui-1.10.4.custom.min.css'))
        fragment.add_css_url(self.runtime.local_resource_url(self,
            'public/css/drag_and_drop.css'))
        fragment.add_javascript_url(self.runtime.local_resource_url(self,
            'public/js/vendor/jquery-ui-1.10.4.custom.min.js'))
        fragment.add_javascript_url(self.runtime.local_resource_url(self,
            'public/js/vendor/jquery.html5-placeholder-shim.js'))
        fragment.add_javascript_url(self.runtime.local_resource_url(self,
            'public/js/vendor/handlebars-v1.1.2.js'))
        fragment.add_javascript_url(self.runtime.local_resource_url(self,
            'public/js/drag_and_drop.js'))

        fragment.initialize_js('DragAndDropBlock')

        return fragment

    def studio_view(self, context):
        """
        Editing view in Studio
        """

        js_templates = load_resource('/templates/html/js_templates.html')
        context = {
            'js_templates': js_templates,
            'self': self,
            'data': urllib.quote(json.dumps(self.data)),
        }

        fragment = Fragment()
        fragment.add_content(render_template('/templates/html/drag_and_drop_edit.html', context))
        fragment.add_css_url(self.runtime.local_resource_url(self,
            'public/css/vendor/jquery-ui-1.10.4.custom.min.css'))
        fragment.add_css_url(self.runtime.local_resource_url(self,
            'public/css/drag_and_drop_edit.css'))
        fragment.add_javascript_url(self.runtime.local_resource_url(self,
            'public/js/vendor/jquery-ui-1.10.4.custom.min.js'))
        fragment.add_javascript_url(self.runtime.local_resource_url(self,
            'public/js/vendor/jquery.html5-placeholder-shim.js'))
        fragment.add_javascript_url(self.runtime.local_resource_url(self,
            'public/js/vendor/handlebars-v1.1.2.js'))
        fragment.add_javascript_url(self.runtime.local_resource_url(self,
            'public/js/drag_and_drop_edit.js'))

        fragment.initialize_js('DragAndDropEditBlock')

        return fragment

    @XBlock.json_handler
    def studio_submit(self, submissions, suffix=''):
        self.display_name = submissions['display_name']
        self.question_text = submissions['question_text']
        self.weight = float(submissions['weight'])
        self.data = submissions['data']

        return {
            'result': 'success',
        }

    @XBlock.handler
    def get_data(self, request, suffix=''):
        data = copy.deepcopy(self.data)

        for item in data['items']:
            # Strip answers
            del item['feedback']
            del item['zone']

        if not self._is_finished():
            del data['feedback']['finish']

        data['state'] = {
            'items': self.item_state,
            'finished': self._is_finished()
        }

        return webob.response.Response(body=json.dumps(data))

    @XBlock.json_handler
    def do_attempt(self, attempt, suffix=''):
        item = next(i for i in self.data['items'] if i['id'] == attempt['val'])
        tot_items = sum(1 for i in self.data['items'] if i['zone'] != 'none')

        final_feedback = None
        is_correct = False

        if item['zone'] == attempt['zone']:
            self.item_state[item['id']] = (attempt['top'], attempt['left'])

            is_correct = True

            if self._is_finished():
                final_feedback = self.data['feedback']['finish']

            # don't publish the grade if the student has already completed the exercise
            if not self.completed:
                if self._is_finished():
                    self.completed = True
                try:
                    self.runtime.publish(self, 'grade', {
                        'value': len(self.item_state) / float(tot_items) * self.weight,
                        'max_value': self.weight,
                    })
                except NotImplementedError:
                    # Note, this publish method is unimplemented in Studio runtimes,
                    # so we have to figure that we're running in Studio for now
                    pass

        self.runtime.publish(self, 'xblock.drag-and-drop-v2.item.dropped', {
            'user_id': self.runtime.user_id,
            'item_id': item['id'],
            'location': attempt['zone'],
            'is_correct': is_correct,
        })

        return {
            'correct': is_correct,
            'finished': self._is_finished(),
            'final_feedback': final_feedback,
            'feedback': item['feedback']['correct'] if is_correct else item['feedback']['incorrect']
        }

    @XBlock.json_handler
    def reset(self, data, suffix=''):
        self.item_state = {}
        return {'result':'success'}

    def _is_finished(self):
        """All items are at their correct place"""
        tot_items = sum(1 for i in self.data['items'] if i['zone'] != 'none')
        return len(self.item_state) == tot_items

    @XBlock.json_handler
    def publish_event(self, data, suffix=''):
        try:
            event_type = data.pop('event_type')
        except KeyError as e:
            return {'result': 'error', 'message': 'Missing event_type in JSON data'}

        data['user_id'] = self.runtime.user_id

        self.runtime.publish(self, event_type, data)
        return {'result':'success'}

    @staticmethod
    def workbench_scenarios():
        """A canned scenario for display in the workbench."""
        return [("Drag-and-drop-v2 scenario", "<vertical_demo><drag-and-drop-v2/></vertical_demo>")]
