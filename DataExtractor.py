#
# DataExtractor - Find datas within (almost) ALL files.
# Copyright (c) 2021 Gwendal Le Coguic
#
# Based on: BurpLinkFinder - Find links within JS files. https://github.com/InitRoot/BurpJSLinkFinder
# Credit to https://github.com/PortSwigger/js-link-finder/blob/master/FransLinkfinder.py for the original extension
# Credit to https://github.com/GerbenJavado/LinkFinder for the idea and regex
#

import re
import json
import base64
import binascii
from urlparse import *

from burp import IBurpExtender, IScannerCheck, ITab

from java.lang import Runnable

from java.awt import EventQueue
from java.awt import Font, Color, Dimension
from java.awt.event import FocusListener

from javax.swing import JLabel
from javax.swing import JTextArea
from javax.swing import JTextField
from javax.swing import JFileChooser
from javax.swing import JButton
from javax.swing import JCheckBox
from javax.swing import JPanel
from javax.swing import JTabbedPane
from javax.swing import JScrollPane
from javax.swing import JSplitPane
from javax.swing import GroupLayout


EXTENSION_HELP = """A click on any "Apply changes" button will save all your settings.

- Settings / Follow scope rules:
do not parse out of scope urls as defined in the target scope tab

- Settings / Remove duplicates:
remove duplicates from datas tabs

- Settings / Ignore extensions:
do not parse urls with those extensions

- Settings / Ignore files:
do not parse those files (regexp allowed), JSON format: ["jquery.min.js",".png",...]

- Custom tab / Config:
list of regexp to search, JSON format: {"key1":"regexp1","?key2":"regexp2",...}
if the first character of the key is a '?'or a '*', the key will not be printed in the datas tab

- Custom tab / Exclude:
remove those results from datas tab (regexp allowed), JSON format: ["http://$","application/javacript",...]
"""

EXTENSION_ABOUT = """Created by Gwendal Le Coguic
https://twitter.com/gwendallecoguic
https://github.com/gwen001
https://github.com/gwen001/DataExtractor
"""

EXTENSION_SETTINGS_KEY = "DataExtractorSettings"
DEFAULT_SETTINGS_REMOVE_DUPLICATES = True
DEFAULT_SETTINGS_SCOPE_ONLY = True
DEFAULT_SETTINGS_IGNORE_EXTENSIONS = "css,ico,gif,jpg,jpeg,png,bmp,svg,avi,mpg,mpeg,mp3,m3u8,woff,woff2,ttf,eot,mp3,mp4,wav,mpg,mpeg,avi,mov,wmv,doc,xls,pdf,zip,tar,7z,rar,tgz,gz,exe,rtp"
DEFAULT_SETTINGS_IGNORE_FILES = ""
# DEFAULT_SETTINGS_IGNORE_EXTENSIONS = ['css','ico','gif','jpg','jpeg','png','bmp','svg','avi','mpg','mpeg','mp3','m3u8','woff','woff2','ttf','eot','mp3','mp4','wav','mpg','mpeg','avi','mov','wmv','doc','xls','pdf','zip','tar','7z','rar','tgz','gz','exe','rtp']



# Using the Runnable class for thread-safety with Swing
class Run(Runnable):
    def __init__(self, runner):
        self.runner = runner

    def run(self):
        self.runner()


class BurpExtender(IBurpExtender, IScannerCheck, ITab, FocusListener):
    def registerExtenderCallbacks(self, callbacks):
        self._callbacks = callbacks
        self._helpers = callbacks.getHelpers()
        self._callbacks.setExtensionName("DataExtractor")

        self.initSettings()

        self._callbacks.registerScannerCheck(self)
        self.initUI()
        self._callbacks.addSuiteTab(self)

        print("DataExtractor loaded.")
        print("Copyright (c) 2021 Gwendal Le Coguic")

    def initUI(self):
        self.tabCounter = 0
        self.extractors = {}

        self.extensionPane = JTabbedPane()
        self.extensionPane.setName("Extension")

        self.loadSettings()
        self.drawSettingsTab()

        for k,item in self._settings["extractors"].items():
            self.addNewTab(item["name"],item["config"],item["exclude"])

        self.addNewButton()

    def drawSettingsTab(self):
        self.wholeShitPane = JSplitPane(JSplitPane.HORIZONTAL_SPLIT)
        self.wholeShitPane.setName("Settings")

        self.settingsPane = JPanel()
        self.settingsPane.setLayout(None)

        self.settingsScopeOptionButton = JCheckBox("Follow scope rules (recommended)")
        self.settingsScopeOptionButton.setSelected(self._settings["scopeOnly"])
        self.settingsScopeOptionButton.setBounds(10, 10, 250, 30)
        self.settingsPane.add( self.settingsScopeOptionButton )

        self.settingsRemoveDuplicatesButton = JCheckBox("Remove duplicates")
        self.settingsRemoveDuplicatesButton.setSelected(self._settings["removeDuplicates"])
        self.settingsRemoveDuplicatesButton.setBounds(10, 45, 250, 30)
        self.settingsPane.add( self.settingsRemoveDuplicatesButton )

        self.settingsIgnoreExtensionsLabel = JLabel("Ignore extensions:")
        self.settingsIgnoreExtensionsLabel.setBounds(10, 90, 150, 30)
        self.settingsPane.add( self.settingsIgnoreExtensionsLabel )

        self.settingsIgnoreExtensionsText = JTextField( self._settings["ignoreExtensions"] )
        self.settingsIgnoreExtensionsText.setBounds(150, 90, 400, 30)
        self.settingsPane.add( self.settingsIgnoreExtensionsText )

        self.settingsIgnoreFilesLabel = JLabel("Ignore files:")
        self.settingsIgnoreFilesLabel.setBounds(10, 130, 150, 30)
        self.settingsPane.add( self.settingsIgnoreFilesLabel )

        self.settingsIgnoreFilesTextArea = JTextArea( self._settings["ignoreFiles"] )
        # self.settingsIgnoreFilesTextArea.setEditable(False)
        self.settingsIgnoreFilesTextArea.setFont(Font("Consolas", Font.PLAIN, 12))

        self.settingsIgnoreFilesPane = JScrollPane(self.settingsIgnoreFilesTextArea)
        self.settingsIgnoreFilesPane.setBounds(10, 155, 550, 250)
        self.settingsPane.add( self.settingsIgnoreFilesPane )

        self.settingsSaveButton = JButton("Apply changes", actionPerformed=self.saveSettings)
        self.settingsSaveButton.setBounds(10, 440, 150, 30)
        self.settingsPane.add( self.settingsSaveButton )

        self.settingsResetButton = JButton("Reset extension", actionPerformed=self.resetSettings)
        self.settingsResetButton.setBounds(200, 440, 150, 30)
        self.settingsResetButton.setForeground(Color(255,255,255))
        self.settingsResetButton.setBackground(Color(255,102,52))
        self.settingsPane.add( self.settingsResetButton )

        resetWarning1 = JLabel("Warning: you're gonna lose all your datas.")
        resetWarning1.setBounds(200, 465, 350, 30)
        self.settingsPane.add( resetWarning1 )

        resetWarning2 = JLabel("Extension reload required.")
        resetWarning2.setBounds(200, 480, 350, 30)
        self.settingsPane.add( resetWarning2 )

        self.helpAboutPane = JPanel()
        self.helpAboutPane.setLayout(None)

        helpLabel = JLabel("Help:")
        helpLabel.setBounds(10, 10, 500, 30)
        helpLabel.setFont(Font("Tahoma", Font.BOLD, 14))
        helpLabel.setForeground(Color(255,102,52))
        self.helpAboutPane.add( helpLabel )

        self.helpTextArea = JTextArea(EXTENSION_HELP)
        self.helpTextArea.setEditable(False)
        self.helpTextArea.setFont(Font("Consolas", Font.PLAIN, 12))

        self.helpPane = JScrollPane(self.helpTextArea)
        self.helpPane.setBounds(10, 50, 650, 350)
        self.helpAboutPane.add( self.helpPane )

        aboutLabel = JLabel("About:")
        aboutLabel.setBounds(10, 450, 500, 30)
        aboutLabel.setFont(Font("Tahoma", Font.BOLD, 14))
        aboutLabel.setForeground(Color(255,102,52))
        self.helpAboutPane.add( aboutLabel )

        self.aboutTextArea = JTextArea(EXTENSION_ABOUT)
        self.aboutTextArea.setEditable(False)
        self.aboutTextArea.setFont(Font("Consolas", Font.PLAIN, 12))

        self.aboutPane = JScrollPane(self.aboutTextArea)
        self.aboutPane.setBounds(10, 490, 650, 150)
        self.helpAboutPane.add( self.aboutPane )

        self.wholeShitPane.setLeftComponent(self.settingsPane)
        self.wholeShitPane.setRightComponent(self.helpAboutPane)
        self.wholeShitPane.setResizeWeight(0.5)

        self.extensionPane.addTab("Settings", self.wholeShitPane)

    def addNewButton(self):
        self.newPane = JPanel()
        self.newPane.setName("...")
        self.newPane.addFocusListener(self)
        self.extensionPane.addTab("...", self.newPane)
        return None

    def focusGained(self, event):
        self.addNewTab()

    def addNewTab(self, name=None, config=None, exclude=None):
        self.tabCounter = self.tabCounter + 1
        if name is None:
            name = str(self.tabCounter)
        print("New tab: id="+str(self.tabCounter)+", name="+name)
        self.extractors[self.tabCounter] = Extractor(self, self.tabCounter, name, config, exclude)
        self.extensionPane.insertTab(name, None, self.extractors[self.tabCounter].mainPane, None, self.tabCounter)
        self.extensionPane.setSelectedIndex(self.tabCounter)

    def initSettings(self):
        self._settings = {}
        self._settings["extractors"] = {}
        self._settings["scopeOnly"] = DEFAULT_SETTINGS_SCOPE_ONLY
        self._settings["removeDuplicates"] = DEFAULT_SETTINGS_REMOVE_DUPLICATES
        self._settings["ignoreExtensions"] = DEFAULT_SETTINGS_IGNORE_EXTENSIONS
        self._settings["ignoreFiles"] = DEFAULT_SETTINGS_IGNORE_FILES

    def resetSettings(self, event):
        self._callbacks.saveExtensionSetting(EXTENSION_SETTINGS_KEY,None)
        # Remove tabs ? Reload settings ?
        print("Settings resetted.")
        self.initSettings()
        self.postLoadSettings()

    def saveSettings(self, event):
        self._settings["scopeOnly"] = self.settingsScopeOptionButton.isSelected()
        self._settings["removeDuplicates"] = self.settingsRemoveDuplicatesButton.isSelected()
        self._settings["ignoreExtensions"] = self.settingsIgnoreExtensionsText.text

        self._settings["ignoreFiles"] = self.settingsIgnoreFilesTextArea.text
        if len(self.settingsIgnoreFilesTextArea.text):
            try:
                j = json.loads(self.settingsIgnoreFilesTextArea.text)
                self._settings["_ignoreFiles"] = j
            except ValueError as e:
                print("Invalid JSON format! (settings:ignoreFiles)")

        self._settings["extractors"] = {}

        for i in range(1,len(self.extractors)+1):
            self.extensionPane.setTitleAt(i,self.extractors[i].tabNameText.text)
            self.extractors[i].name = self.extractors[i].tabNameText.text
            # self.extractors[i].mainPane.setName( self.extractors[i].tabNameText.text )
            self._settings["extractors"][i] = {}
            # self._settings["extractors"][i]["id"] = self.extractors[i].id
            self._settings["extractors"][i]["name"] = self.extractors[i].name
            self._settings["extractors"][i]["config"] = self.extractors[i].configTextArea.text
            self._settings["extractors"][i]["exclude"] = self.extractors[i].excludeTextArea.text

        to_save = {}
        to_save["scopeOnly"] = self._settings["scopeOnly"]
        to_save["removeDuplicates"] = self._settings["removeDuplicates"]
        to_save["ignoreExtensions"] = self._settings["ignoreExtensions"]
        to_save["ignoreFiles"] = self._settings["ignoreFiles"]
        to_save["extractors"] = self._settings["extractors"]

        self._callbacks.saveExtensionSetting(EXTENSION_SETTINGS_KEY,json.dumps(to_save))
        print(to_save)
        print("Settings saved.")
        self.postLoadSettings()

    def loadSettings(self):
        settings = self._callbacks.loadExtensionSetting(EXTENSION_SETTINGS_KEY)

        if settings:
            print("Previous settings found.")
            try:
                settings = json.loads(settings)
                print("Settings loaded.")
            except ValueError as e:
                settings = {}
                print("Settings are not valid JSON format!")
        else:
            settings = {}
            print("No settings found.")

        if "scopeOnly" in settings:
            self._settings["scopeOnly"] = settings["scopeOnly"]
        if "removeDuplicates" in settings:
            self._settings["removeDuplicates"] = settings["removeDuplicates"]
        if "ignoreExtensions" in settings:
            self._settings["ignoreExtensions"] = settings["ignoreExtensions"]
        if "ignoreFiles" in settings:
            self._settings["ignoreFiles"] = settings["ignoreFiles"]
        if "extractors" in settings:
            self._settings["extractors"] = settings["extractors"]

        self.postLoadSettings()

    def postLoadSettings(self):
        self._settings["_ignoreExtensions"] = []
        for ext in self._settings["ignoreExtensions"].split(","):
            self._settings["_ignoreExtensions"].append("."+ext)
        # print(self._settings["_ignoreExtensions"])

        self._settings["_ignoreFiles"] = []
        self._settings["__ignoreFiles"] = []
        if len(self._settings["ignoreFiles"]):
            try:
                j = json.loads(self._settings["ignoreFiles"])
                self._settings["_ignoreFiles"] = j
                for r in self._settings["_ignoreFiles"]:
                    self._settings["__ignoreFiles"].append( re.compile(r, re.IGNORECASE) )
            except ValueError as e:
                print("Invalid JSON format! (settings:ignoreFiles)")

    def doPassiveScan(self, ihrr):
        try:
            requestURL = ihrr.getUrl()
            stringURL = str(requestURL)
            t_url = urlparse(stringURL)
            print("Scanning: "+stringURL)
            # print(t_url.path)

            if not self.checkScope(requestURL):
                return None
            if not self.checkExtension(t_url.path):
                return None
            if not self.checkFile(stringURL):
                return None

            print("Grepping: "+stringURL)

            for i in range(1,len(self.extractors)+1):
                self.extractors[i].scan(ihrr)
        except UnicodeEncodeError:
            print("Error in URL decode.")

        return None

    def checkFile(self, url):
        for regexp in self._settings["__ignoreFiles"]:
            if re.search(regexp,url):
                print("File ignored: "+url)
                return False

        print("File not ignored: "+url)
        return True

    def checkScope(self, url):
        print("scope check: "+str(url))
        if self._settings["scopeOnly"] and not(self._callbacks.isInScope(url)):
            print("OOS: "+str(url))
            return False

        print("Scope OK: "+str(url))
        return True

    def checkExtension(self, path):
        print("extension check: "+path)
        for ext in self._settings["_ignoreExtensions"]:
            if path.endswith(ext):
                print("Extension ignored: "+path)
                return False

        print("Extension OK: "+path)
        return True

    def getTabCaption(self):
        return "DataExtractor"

    def getUiComponent(self):
        return self.extensionPane

    def consolidateDuplicateIssues(self, isb, isa):
        return -1

    def extensionUnloaded(self):
        print("DataExtractor unloaded.")
        return


class Extractor():

    def __init__(self, extender, eid, name, config=None, exclude=None):
        self.extender = extender
        self.id = eid
        self.name = name
        self.config = config
        self._config = []
        self.__config = {}
        self.exclude = exclude
        self._exclude = []
        self.__exclude = []
        self.initUI()

        if config and len(config):
            self.configTextArea.text = self.config
            try:
                j = json.loads(config)
                self._config = j
                self.__config = {}
                for k,r in self._config.items():
                    self.__config[k] = re.compile(r,re.IGNORECASE)
            except ValueError as e:
                print("Invalid JSON format! ("+self.name+":config)")

        if exclude and len(exclude):
            self.excludeTextArea.text = self.exclude
            try:
                j = json.loads(exclude)
                self._exclude = j
                self.__exclude = []
                for r in self._exclude:
                    self.__exclude.append( re.compile(r,re.IGNORECASE) )
            except ValueError as e:
                print("Invalid JSON format! ("+self.name+":exclude)")

    def initUI(self):
        self.mainPane = JSplitPane(JSplitPane.HORIZONTAL_SPLIT)

        self.configLabel = JLabel("Config:")
        self.configLabel.setFont(Font("Tahoma", Font.BOLD, 14))
        self.configLabel.setForeground(Color(255,102,52))

        self.tabNameText = JTextField(self.name)
        dim = Dimension(170, 25)
        self.tabNameText.setSize(dim)
        self.tabNameText.setMaximumSize(dim)
        self.tabNameText.setPreferredSize(dim)

        self.saveSettingsButton = JButton("Apply changes", actionPerformed=self.saveSettings)

        self.deleteTabButton = JButton("Remove this tab", actionPerformed=self.saveSettings)
        self.deleteTabButton.setForeground(Color(255,255,255))
        self.deleteTabButton.setBackground(Color(255,102,52))

        self.configTextArea = JTextArea("")
        self.configTextArea.setFont(Font("Consolas", Font.PLAIN, 12))
        self.configTextArea.setLineWrap(True)

        self.configPanel = JScrollPane()
        self.configPanel.setViewportView(self.configTextArea)

        self.excludeLabel = JLabel("Exclude:")
        self.excludeLabel.setFont(Font("Tahoma", Font.BOLD, 14))
        self.excludeLabel.setForeground(Color(255,102,52))

        self.excludeTextArea = JTextArea("")
        self.excludeTextArea.setFont(Font("Consolas", Font.PLAIN, 12))
        self.excludeTextArea.setLineWrap(True)

        self.excludePanel = JScrollPane()
        self.excludePanel.setViewportView(self.excludeTextArea)

        self.leftPane = JPanel()
        leftLayout = GroupLayout(self.leftPane)
        leftLayout.setAutoCreateGaps(True)
        leftLayout.setAutoCreateContainerGaps(True)
        self.leftPane.setLayout(leftLayout)

        leftLayout.setHorizontalGroup(
            leftLayout.createSequentialGroup()
            .addGroup(leftLayout.createParallelGroup()
                    .addGroup(leftLayout.createSequentialGroup()
                        .addComponent(self.configLabel)
                        .addGap(150)
                        .addComponent(self.tabNameText)
                        .addComponent(self.saveSettingsButton)
                        .addComponent(self.deleteTabButton)
                    )
                    .addComponent(self.configPanel)
                    .addComponent(self.excludeLabel)
                    .addComponent(self.excludePanel)
            )
        )

        leftLayout.setVerticalGroup(
            leftLayout.createSequentialGroup()
            .addGroup(leftLayout.createParallelGroup()
                .addGroup(leftLayout.createParallelGroup(GroupLayout.Alignment.BASELINE)
                    .addComponent(self.configLabel)
                    .addComponent(self.tabNameText)
                    .addComponent(self.saveSettingsButton)
                    .addComponent(self.deleteTabButton)
                )
            )
            .addGroup(leftLayout.createParallelGroup()
                    .addComponent(self.configPanel)
            )
            .addGroup(leftLayout.createParallelGroup()
                    .addComponent(self.excludeLabel)
            )
            .addGroup(leftLayout.createParallelGroup()
                    .addComponent(self.excludePanel)
            )
        )

        self.datasLabel = JLabel("Datas:")
        self.datasLabel.setFont(Font("Tahoma", Font.BOLD, 14))
        self.datasLabel.setForeground(Color(255,102,52))

        self.exportButton = JButton("Export this datas tab", actionPerformed=self.exportDatas)

        self.clearButton = JButton("Clear this datas tab", actionPerformed=self.clearDatas)
        self.clearButton.setForeground(Color(255,255,255))
        self.clearButton.setBackground(Color(255,102,52))

        self.datasTextArea = JTextArea("")
        self.datasTextArea.setFont(Font("Consolas", Font.PLAIN, 12))
        self.datasTextArea.setEditable(False)
        self.datasTextArea.setLineWrap(True)

        self.datasPanel = JScrollPane()
        self.datasPanel.setViewportView(self.datasTextArea)

        self.rightPane = JPanel()
        rightLayout = GroupLayout(self.rightPane)
        rightLayout.setAutoCreateGaps(True)
        rightLayout.setAutoCreateContainerGaps(True)
        self.rightPane.setLayout(rightLayout)

        rightLayout.setHorizontalGroup(
            rightLayout.createSequentialGroup()
            .addGroup(rightLayout.createParallelGroup()
                    .addGroup(rightLayout.createSequentialGroup()
                        .addComponent(self.datasLabel)
                        .addGap(150)
                        .addComponent(self.exportButton)
                        .addComponent(self.clearButton)
                    )
                    .addComponent(self.datasPanel)
            )
        )

        rightLayout.setVerticalGroup(
            rightLayout.createSequentialGroup()
            .addGroup(rightLayout.createParallelGroup()
                .addGroup(rightLayout.createParallelGroup(GroupLayout.Alignment.BASELINE)
                    .addComponent(self.datasLabel)
                    .addComponent(self.exportButton)
                    .addComponent(self.clearButton)
                )
            )
            .addGroup(rightLayout.createParallelGroup()
                    .addComponent(self.datasPanel)
            )
        )

        self.mainPane.setLeftComponent(self.leftPane)
        self.mainPane.setRightComponent(self.rightPane)
        self.mainPane.setResizeWeight(0.3)

    def saveSettings(self, event):
        self.config = self.configTextArea.text
        self._config = []
        self.__config = {}
        if len(self.configTextArea.text):
            try:
                j = json.loads(self.configTextArea.text)
                self._config = j
                for k,r in self._config.items():
                    self.__config[k] = re.compile(r,re.IGNORECASE)
            except ValueError as e:
                print("Invalid JSON format! ("+self.name+":config)")

        self.exclude = self.excludeTextArea.text
        self._exclude = []
        self.__exclude = []
        if len(self.excludeTextArea.text):
            try:
                j = json.loads(self.excludeTextArea.text)
                self._exclude = j
                for r in self._exclude:
                    self.__exclude.append( re.compile(r,re.IGNORECASE) )
            except ValueError as e:
                print("Invalid JSON format! ("+self.name+":exclude)")

        self.extender.saveSettings(event)

    def clearDatas(self, event):
        # return None
        self.datasTextArea.setText("")

    def exportDatas(self, event):
        chooseFile = JFileChooser()
        ret = chooseFile.showDialog(self.extender.extensionPane, "Choose file")
        filename = chooseFile.getSelectedFile().getCanonicalPath()
        print("Export \""+self.name+"\" to : " + filename)
        open(filename, 'w', 0).write(self.datasTextArea.text)

    def scan(self, ihrr):
        t_results = []
        t_filtered = []
        t_nodups = []
        t_final = []
        t_keepkeys = {}
        encoded_resp = binascii.b2a_base64(ihrr.getResponse())
        decoded_resp = base64.b64decode(encoded_resp)
        # print(len(encoded_resp))
        # print(len(decoded_resp))

        for k,regexp in self.__config.items():
            # print(regexp)
            # r = re.search(regexp,decoded_resp)
            for m in re.finditer(regexp,decoded_resp):
                # print(m.group(1))
                t_results.append( m.group(1) )
                if not k.startswith("*") and not k.startswith("?"):
                    t_keepkeys[m.group(1)] = k

        print(self.name+": "+str(len(t_results))+" results.")

        for r in t_results:
            exclude_flag = False
            for regexp in self.__exclude:
                if re.search(regexp,r):
                    exclude_flag = True
            if not exclude_flag:
                t_filtered.append( r )

        print(self.name+": "+str(len(t_filtered))+" filtered ("+str(len(t_results)-len(t_filtered))+" removed).")

        if len(t_filtered):
            if self.extender._settings["removeDuplicates"]:
                t_currentdatas = self.datasTextArea.text.split("\n")

                for r in t_filtered:
                    if not r in t_currentdatas and not r in t_nodups:
                        t_nodups.append( r )

                print(self.name+": "+str(len(t_nodups))+" undups ("+str(len(t_filtered)-len(t_nodups))+" removed).")
                t_final = t_nodups
            else:
                t_final = t_filtered

        if len(t_final):
            for r in t_final:
                o = ""
                if r in t_keepkeys:
                    o = t_keepkeys[r] + ": "
                o = o + r + "\n"
                self.datasTextArea.append( o )

        return len(t_final)

        # print(self.name+": "+str(url))

        # t_results = []
        # # url = self.reqres.getUrl()
        # encoded_resp = binascii.b2a_base64(self.reqres.getResponse())
        # decoded_resp = base64.b64decode(encoded_resp)

        # for r in RegexpList:
        #     endpoints = self.parser_file(decoded_resp, r)
        #     for e in endpoints:
        #        t_results.append(e)

        # return t_results


        # linkA = linkAnalyse(ihrr,self._helpers)

        # if any(x in stringURL for x in JSExclusionList):
        #     print("[-] URL excluded " + str(requestURL))
        # else:
        #     self.datasTextArea.append(stringURL+"\n")
        #     issueText = linkA.analyseURL()
        #     for counter, issueText in enumerate(issueText):
        #         if issueText['link'] is not None:
        #             self.datasTextArea.append(issueText['link']+"\n")
        #     return None



# class linkAnalyse():
#     def __init__(self, reqres, helpers):
#         self._helpers = helpers
#         self.reqres = reqres

#     def analyseURL(self):
#         mime_type = self._helpers.analyzeResponse(self.reqres.getResponse()).getStatedMimeType()
#         # print(str(mime_type))

#         # if mime_type.lower() == 'script':
#         for t in MimeTypeExclusionList:
#             if t == mime_type.lower():
#                 print("skipping mime type "+t+" -> "+str(mime_type))
#                 return []

#         print("analyzing... "+str(mime_type))
#         t_endpoints = []
#         url = self.reqres.getUrl()
#         encoded_resp = binascii.b2a_base64(self.reqres.getResponse())
#         decoded_resp = base64.b64decode(encoded_resp)

#         for r in RegexpList:
#             endpoints = self.parser_file(decoded_resp, r)
#             for e in endpoints:
#                t_endpoints.append(e)

#         return t_endpoints

#     def	parser_file(self, content, regex_str, mode=1, more_regex=None, no_dup=1):
#         regex = re.compile(regex_str, re.VERBOSE)
#         items = [{"link": m.group(1)} for m in re.finditer(regex, content)]

#         if no_dup:
#             # Remove duplication
#             all_links = set()
#             no_dup_items = []
#             for item in items:
#                 if item["link"] not in all_links:
#                     all_links.add(item["link"])
#                     no_dup_items.append(item)
#             items = no_dup_items

#         # Match Regex
#         filtered_items = []

#         for item in items:
#             # Remove other capture groups from regex results
#             if more_regex:
#                 if re.search(more_regex, item["link"]):
#                     filtered_items.append(item)
#             else:
#                 filtered_items.append(item)

#         return filtered_items


if __name__ in ('__main__', 'main'):
    EventQueue.invokeLater(Run(BurpExtender))
