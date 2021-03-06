import sys
import os

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qsci import QsciScintilla, QsciLexerCustom, QsciAPIs, QsciLexerPython


import command
import qgis_commands

reload(command)
reload(qgis_commands)

_start_prompt = "-> "

import logger

# logger.msg('Test message from qgiscommand.py')


class SourceViewer(QsciScintilla):
    def __init__(self, syntax='Python', parent=None):
        super(SourceViewer, self).__init__(parent)
        if syntax == 'Python':
            self.lex = QsciLexerPython(self)
            self.setLexer(self.lex)
        self.setReadOnly(True)

    def setText(self, text, line=0):
        super(SourceViewer, self).setText(text)
        self.setFirstVisibleLine(line)


def show_viewer(text, lineno=0, title='', syntax='Python'):
    dlg = QDialog()
    dlg.setWindowTitle(title)
    dlg.setLayout(QGridLayout())
    dlg.layout().setContentsMargins(0, 0, 0, 0)
    view = SourceViewer(syntax)
    dlg.layout().addWidget(view)
    view.setText(text, lineno)
    view.resize(500, 500)
    dlg.exec_()


@command.command("Command name")
@command.check(name=command.is_comamnd)
def command_help(name):
    """
    Lookup the help for a given command
    """
    helptext = command.help_text[name]
    show_viewer(helptext, title="Help for {}".format(name), syntax='')

@command.command("Command name")
@command.check(name=command.is_comamnd)
def view_source(name):
    """
    Lookup the source code for a given command
    """
    func = command.commands[name]
    filename, lineno = command.sourcelookup[name]
    with open(filename, "r") as f:
        source = f.read()
    show_viewer(source, line, filename)

class Lexer(QsciLexerCustom):
    """
    Note: Crashes at the momemnt
    """
    def __init__(self, parent=None):
        QsciLexerCustom.__init__(self, parent)
        self._styles = {
            0: 'Default',
            1: 'Function',
            }
        for key, value in self._styles.iteritems():
            setattr(self, value, key)

    def description(self, style):
        return self._styles.get(style, 'Default')

    def defaultColor(self, style):
        if style == self.Default:
            return QColor('#000000')
        elif style == self.Function:
            return QColor('#C0C0C0')
        return QsciLexerCustom.defaultColor(self, style)

    def styleText(self, start, end):
        print start, end


class CommandShell(QsciScintilla):
    def __init__(self, parent=None):
        super(CommandShell, self).__init__(parent)
        self.setMinimumHeight(50)
        self.setMaximumHeight(50)
        self.settings = QSettings()
        self.lex = QsciLexerPython(self)
        self.apis = QsciAPIs(self.lex)
        self.lex.setAPIs(self.apis)
        self.setLexers()
        self.SendScintilla(QsciScintilla.SCI_SETHSCROLLBAR, 0)
        self.SendScintilla(QsciScintilla.SCI_SETVSCROLLBAR, 0)
        self.setFolding(0)
        self._start_prompt = _start_prompt
        self.prompt = self._start_prompt
        self.currentfunction = None
        self.setAutoCompletionSource(self.AcsAPIs)
        self.setAutoCompletionThreshold(1)
        self.setAutoCompletionReplaceWord(True)
        self.setCallTipsStyle(QsciScintilla.CallTipsNoContext)
        self.parent().installEventFilter(self)
        self.textChanged.connect(self.text_changed)
        self._lastcompletions = None

    def text_changed(self):
        if not self.get_data().strip():
            return

        try:
            completions = command.completions_for_line(self.get_data())
            if completions == self._lastcompletions:
                self.autoCompleteFromAPIs()
                return

            self._lastcompletions = completions

            self.apis.cancelPreparation()
            self.apis.clear()
            for value in completions:
                data = u"{}".format(value)
                self.apis.add(data)

            self.apis.prepare()
        except command.NoFunction:
            return

    def end(self):
        self.parent().removeEventFilter(self)
        self.close()

    def eventFilter(self, object, event):
        if event.type() == QEvent.Resize:
            self.adjust_size()
        return QWidget.eventFilter(self, object, event)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.entered()
        elif e.key() == Qt.Key_Escape:
            self.close()
        elif e.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            _, newindex = self.getCursorPosition()
            if newindex > len(self.prompt):
                QsciScintilla.keyPressEvent(self, e)
        else:
            QsciScintilla.keyPressEvent(self, e)

    def show_prompt(self, prompt=_start_prompt, data=None):
        self.clear()
        if not prompt == _start_prompt:
            prompt += ":"

        text = prompt

        if data:
            text = prompt + str(data)

        self.setText(text)
        self.prompt = prompt
        self.move_cursor_to_end()

    def get_end_pos(self):
        """Return (line, index) position of the last character"""
        line = self.lines() - 1
        return (line, len(self.text(line)))

    def move_cursor_to_end(self):
        """Move cursor to end of text"""
        line, index = self.get_end_pos()
        self.setCursorPosition(line, index)
        self.ensureCursorVisible()
        self.ensureLineVisible(line)

    def get_data(self):
        line = self.text()
        line = line[len(self.prompt):]
        return line

    def entered(self):
        line = self.get_data()
        if not self.currentfunction:
            try:
                gen = command.parse_line_data(line)
            except command.NoFunction:
                return

            if gen:
                self.currentfunction = gen
                line = None
            else:
                self.currentfunction = None
                self.show_prompt()
                return

        try:
            prompt, data = self.currentfunction.send(line)
            self.show_prompt(prompt, data)
        except StopIteration:
            self.currentfunction = None
            self.show_prompt()

    def setLexers(self):
        loadFont = self.settings.value("pythonConsole/fontfamilytext", "Monospace")
        fontSize = self.settings.value("pythonConsole/fontsize", 10, type=int)

        font = QFont(loadFont)
        font.setFixedPitch(True)
        font.setPointSize(fontSize)
        font.setStyleHint(QFont.TypeWriter)
        font.setStretch(QFont.SemiCondensed)
        font.setLetterSpacing(QFont.PercentageSpacing, 87.0)
        font.setBold(False)

        self.lex.setFont(font)
        self.lex.setDefaultFont(font)
        self.setLexer(self.lex)

    def adjust_size(self):
        fm = QFontMetrics(self.font())
        self.setMaximumHeight(20)
        self.resize(self.parent().width(), 20)
        self.move(0, self.parent().height() - self.height())

    def showEvent(self, event):
        self.adjust_size()
        self.show_prompt()
        self.setFocus()

    def activated(self):
        visible = self.isVisible()
        self.setVisible(not visible)


if __name__ == "__main__":
    c = CommandShell(iface.mapCanvas())
    c.activated()
