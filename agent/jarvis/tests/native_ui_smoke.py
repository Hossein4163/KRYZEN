"""Run opt-in layout QA in the desktop app's GTK4/WebKit engine against a fixture.
Usage: python3 native_ui_smoke.py http://127.0.0.1:8774
"""
import json
from pathlib import Path
import sys
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('WebKit', '6.0')
from gi.repository import Gtk, WebKit, GLib

class Smoke(Gtk.Application):
    def do_activate(self):
        self.window = Gtk.ApplicationWindow(application=self, title='K.R.Y.Z.E.N UI verification')
        self.window.set_default_size(1100, 900)
        self.view = WebKit.WebView()
        manager = self.view.get_user_content_manager()
        manager.add_script(WebKit.UserScript.new(
            'window.__pageErrors=[];addEventListener("error",e=>__pageErrors.push(e.message));'
            'addEventListener("unhandledrejection",e=>__pageErrors.push(String(e.reason)));',
            WebKit.UserContentInjectedFrames.TOP_FRAME, WebKit.UserScriptInjectionTime.START, None, None))
        self.window.set_child(self.view)
        self.window.present()
        self.started = False
        self.view.connect('load-changed', self.loaded)
        self.view.load_uri(sys.argv[1])
        GLib.timeout_add_seconds(40, self.timeout)

    def loaded(self, view, event):
        if event != WebKit.LoadEvent.FINISHED or self.started:
            return
        self.started = True
        script = Path(__file__).with_name('browser_layout.js').read_text().rstrip().removesuffix(';')
        self.view.evaluate_javascript(script + '.then(r=>window.__qa={result:r,errors:__pageErrors},e=>window.__qa={error:String(e),errors:__pageErrors})', -1)
        GLib.timeout_add(250, self.poll)

    def poll(self):
        self.view.evaluate_javascript('JSON.stringify(window.__qa||null)', -1, None, None, None, self.result)
        return not getattr(self, 'done', False)

    def result(self, view, result):
        try:
            value = json.loads(view.evaluate_javascript_finish(result).to_string())
            if value is None:
                return
            self.done = True
            print(json.dumps(value), flush=True)
            self.failed = bool(value.get('error') or value.get('errors'))
            self.quit()
        except Exception as error:
            print(str(error), file=sys.stderr)
            self.failed = True
            self.quit()

    def timeout(self):
        print('Native UI verification timed out', file=sys.stderr)
        self.failed = True
        self.quit()
        return False

app = Smoke()
app.failed = False
app.run([sys.argv[0]])
raise SystemExit(1 if app.failed else 0)
