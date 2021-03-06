#coding=utf-8
__version__ = 0.1

import shutil

from robofab.world import RFont
from defconAppKit.tools.textSplitter import splitText
from vanilla import Window, List, Slider, CheckBox, EditText, SquareButton, Group, TextBox, Sheet, Tabs
from vanilla.dialogs import getFile
from mojo.UI import MultiLineView
from mojo.events import addObserver, removeObserver

from objects.manager import FiltersManager, makeKey

class PenBallWizard(object):

    def __init__(self):
        self.filters = FiltersManager()
        self.glyphNames = []
        self.cachedFont = RFont(showUI=False)
        self.currentFont = CurrentFont()
        filtersList = self.filters.get()
        if len(self.filters):
            self.currentFilterKey = filtersList[0]
        else:
            self.currentFilterKey = None
        self.fill = True

        self.observers = [
            ('fontChanged', 'fontBecameCurrent'),
        ]

        self.w = Window((600, 400), 'PenBall Wizard v{0}'.format(__version__), minSize=(500, 400))
        self.w.filtersPanel = Group((0, 0, 300, -0))
        self.w.filtersPanel.filtersList = List((0, 0, -0, -40), filtersList, selectionCallback=self.filterSelectionChanged, doubleClickCallback=self.filterEdit, allowsMultipleSelection=False, allowsEmptySelection=False, rowHeight=22)
        self.w.filtersPanel.options = Group((0, -40, -0, 0))
        self.w.filtersPanel.addFilter = SquareButton((0, -40, 150, 40), 'Add filter', sizeStyle='small', callback=self.addFilter)
        self.w.filtersPanel.removeFilter = SquareButton((-150, -40, 150, 40), 'Remove filter', sizeStyle='small', callback=self.removeFilter)
        self.w.filtersPanel.removeFilter.enable(False)
        self.w.textInput = EditText((300, 0, -90, 22), '', callback=self.stringInput)
        self.w.generate = SquareButton((-90, 0, 90, 22), 'Generate', callback=self.generateGlyphs, sizeStyle='small')
        self.w.preview = MultiLineView((300, 22, -0, -0))
        self.w.switchFillStroke = SquareButton((-75, -40, 60, 25), 'Fill', callback=self.switchFillStroke, sizeStyle='small')
        displayStates = self.w.preview.getDisplayStates()
        for key in ['Show Metrics','Upside Down','Stroke','Beam','Inverse','Water Fall','Single Line']:
            displayStates[key] = False
        for key in ['Fill','Multi Line']:
            displayStates[key] = True
        self.w.preview.setDisplayStates(displayStates)

        for callback, event in self.observers:
            addObserver(self, callback, event)

        self.updateOptions()

        self.w.bind('close', self.end)
        self.w.open()

    def generateGlyphs(self, sender):
        font = self.currentFont
        newFont = RFont(showUI=False)
        if font is not None:
            glyphs = [font[glyphName] for glyphName in font.selection if glyphName in font]
            key, arguments = self.getFilterTokens()
            if key is not None:
                filteredGlyphs = []
                for glyph in glyphs:
                    if len(glyph.components) > 0:
                        for comp in glyph.components:
                            baseGlyphName = comp.baseGlyph
                            baseGlyph = font[baseGlyphName]
                            baseFilteredGlyph = baseGlyph.getRepresentation(key, **arguments)
                            newFont.insertGlyph(baseFilteredGlyph, baseGlyphName)
                    filteredGlyph = glyph.getRepresentation(key, **arguments)
                    if filteredGlyph is not None:
                        newFont.insertGlyph(filteredGlyph, glyph.name)
        newFont.showUI()


    def getFilterTokens(self):
        if self.currentFilterKey is not None:
            key = makeKey(self.currentFilterKey)
            currentFilter = self.getCurrentFilter()
            arguments = currentFilter['arguments'] if currentFilter.has_key('arguments') else {}
            return key, arguments
        return None, None

    def updateFiltersList(self):
        filtersList = self.filters.get()
        self.w.filtersPanel.filtersList.set(filtersList)

    def setArgumentValue(self, sender):
        value = sender.get()
        valueType = sender.type
        if valueType == 'bool':
            value = bool(value)
        key = sender.name
        if self.currentFilterKey is not None:
            self.filters.setFilterArgument(self.currentFilterKey, key, value)
        self.updatePreview()

    def processGlyphs(self):
        font = self.currentFont
        if font is not None:
            glyphs = [font[glyphName] for glyphName in self.glyphNames if glyphName in font]
            key, arguments = self.getFilterTokens()
            if key is not None:
                filteredGlyphs = []
                for glyph in glyphs:
                    if len(glyph.components) > 0:
                        for comp in glyph.components:
                            baseGlyphName = comp.baseGlyph
                            baseGlyph = font[baseGlyphName]
                            baseFilteredGlyph = baseGlyph.getRepresentation(key, **arguments)
                            self.cachedFont.insertGlyph(baseFilteredGlyph, baseGlyphName)
                    filteredGlyph = glyph.getRepresentation(key, **arguments)
                    if filteredGlyph is not None:
                        self.cachedFont.insertGlyph(filteredGlyph, glyph.name)
                        filteredGlyphs.append(self.cachedFont[glyph.name])
                return filteredGlyphs
            self.cachedFont = self.currentFont
            return glyphs
        return []

    def updatePreview(self):
        glyphs = self.processGlyphs()
        self.w.preview.setFont(self.cachedFont)
        self.w.preview.set(glyphs)

    def updateOptions(self):
        if hasattr(self.w.filtersPanel, 'options'):
            delattr(self.w.filtersPanel, 'options')
        if self.currentFilterKey is not None:
            currentFilter = self.getCurrentFilter()
            arguments = currentFilter['arguments'] if currentFilter.has_key('arguments') else {}
            limits = currentFilter['limits'] if currentFilter.has_key('limits') else {}
            height = (len(arguments) * 40) + 40
            self.w.filtersPanel.filtersList.setPosSize((0, 0, -0, -height))
            self.w.filtersPanel.options = Group((0, -height, -0, -40))
            for i, (arg, value) in enumerate(arguments.items()):
                attrName = 'option{0}'.format(i)
                valueType = None
                if limits.has_key(arg):
                    mini, maxi = limits[arg]
                else:
                    mini, maxi = 0, 100
                if isinstance(value, bool):
                    setattr(self.w.filtersPanel.options, attrName, CheckBox((15, 15 + (i*30), -15, 22), arg, value=value, callback=self.setArgumentValue, sizeStyle='small'))
                    valueType = 'bool'
                elif isinstance(value, (str, unicode)):
                    setattr(self.w.filtersPanel.options, attrName, EditText((15, 15 + (i*30), -15, 22), value, callback=self.setArgumentValue, sizeStyle='small'))
                elif isinstance(value, (int, float)):
                    setattr(self.w.filtersPanel.options, attrName+'Title', TextBox((15, 18 + (i*30), 150, 22), arg, sizeStyle='small'))
                    setattr(self.w.filtersPanel.options, attrName, Slider((168, 15 + (i*30), -15, 22), minValue=mini, maxValue=maxi, value=value, callback=self.setArgumentValue))
                control = getattr(self.w.filtersPanel.options, attrName)
                control.name = arg
                control.type = valueType

    def stringInput(self, sender):
        text = sender.get()
        if self.currentFont is not None:
            cmap = self.currentFont.getCharacterMapping()
            self.glyphNames = splitText(text, cmap)
        else:
            self.glyphNames = []
        self.updatePreview()

    def filterEdit(self, sender):
        filterName = self.currentFilterKey
        self.buildFilterSheet(filterName)
        self.filterSheet.open()

    def buildFilterSheet(self, filterName='', makeNew=False):
        sheetFields = {
            'fileName': '',
            'modulePath': '',
            'filterObject': '',
            'limits': {},
            'arguments': {},
        }
        if filterName != '':
            filterDict = self.filters[filterName]
            for key in filterDict:
                sheetFields[key] = filterDict[key]

        self.filterSheet = Sheet((0, 0, 400, 350), self.w)
        self.filterSheet.new = makeNew
        applyTitle = 'Add Filter' if filterName == '' else 'Update Filder'
        self.filterSheet.apply = SquareButton((-115, -37, 100, 22), applyTitle, callback=self.processFilter, sizeStyle='small')
        self.filterSheet.cancel = SquareButton((-205, -37, 80, 22), 'Cancel', callback=self.closeFilterSheet, sizeStyle='small')

        y = 20
        self.filterSheet.nameTitle = TextBox((15, y, 100, 22), 'Filter Name')
        self.filterSheet.name = EditText((125, y, -15, 22), filterName)
        y += 22

        tabs = ['module','file']

        y += 20
        self.filterSheet.importPath = Tabs((15, y, -15, 75), tabs)
        modulePath = self.filterSheet.importPath[0]
        filePath = self.filterSheet.importPath[1]

        modulePath.pathInput = EditText((10, 10, -10, -10), sheetFields['modulePath'])
        filePath.pathInput = EditText((10, 10, -110, -10), sheetFields['fileName'])
        if len(sheetFields['modulePath']) > 0:
            self.filterSheet.importPath.set(0)
        elif len(sheetFields['fileName']) > 0:
            self.filterSheet.importPath.set(1)
        filePath.fileInput = SquareButton((-100, 10, 90, -10), u'Add File…', sizeStyle='small', callback=self.getFile)
        y += 75

        y += 10
        self.filterSheet.filterObjectTitle = TextBox((15, y, 100, 22), 'Filter Object (pen, function)')
        self.filterSheet.filterObject = EditText((125, y, -15, 22), sheetFields['filterObject'])
        y += 22

        y += 20
        columns = [
            {'title': 'argument', 'width': 160, 'editable':True},
            {'title': 'value', 'width': 71, 'editable':True},
            {'title': 'min', 'width': 49, 'editable':True},
            {'title': 'max', 'width': 49, 'editable':True}
        ]

        arguments = sheetFields['arguments']
        limits = sheetFields['limits']

        argumentItems = []

        for key, value in arguments.items():
            if isinstance(value, bool):
                value = str(value)
            elif isinstance(value, float):
                value = round(value, 2)
            argItem = {
                'argument': key,
                'value': value
                }
            if limits.has_key(key):
                minimum, maximum = sheetFields['limits'][key]
                argItem['min'] = minimum
                argItem['max'] = maximum

            argumentItems.append(argItem)

        buttonSize = 20
        gutter = 7
        self.filterSheet.arguments = List((15 + buttonSize + gutter, y, -15, -52), argumentItems, columnDescriptions=columns, allowsMultipleSelection=False, allowsEmptySelection=False)
        self.filterSheet.addArgument = SquareButton((15, -52-(buttonSize*2)-gutter, buttonSize, buttonSize), '+', sizeStyle='small', callback=self.addArgument)
        self.filterSheet.removeArgument = SquareButton((15, -52-buttonSize, buttonSize, buttonSize), '-', sizeStyle='small', callback=self.removeArgument)
        if len(argumentItems) == 0:
            self.filterSheet.removeArgument.enable(False)

        if filterName == '':
            self.currentFilterKey = ''

    def addArgument(self, sender):
        argumentsList = self.filterSheet.arguments.get()
        argumentsList.append({'argument': 'rename me', 'value': 50, 'min': 0, 'max': 100})
        if len(argumentsList) > 0:
            self.filterSheet.removeArgument.enable(True)
        self.filterSheet.arguments.set(argumentsList)

    def removeArgument(self, sender):
        argumentsList = self.filterSheet.arguments.get()
        if len(argumentsList) == 0:
            self.filterSheet.removeArgument.enable(False)
        selection = self.filterSheet.arguments.getSelection()[0]
        argumentsList.pop(selection)
        self.filterSheet.arguments.set(argumentsList)

    def getFile(self, sender):
        path = getFile(fileTypes=['py'], allowsMultipleSelection=False, resultCallback=self.loadFilePath, parentWindow=self.filterSheet)

    def loadFilePath(self, paths):
        path = paths[0]
        fileName = path.split('/')[-1]
        folder = '/'.join(__file__.split('/')[:-1])
        dest = '{0}/filterObjects/{1}'.format(folder, fileName)
        shutil.copyfile(path, dest)
        self.filterSheet.importPath[1].pathInput.set(fileName[:-3])

    def closeFilterSheet(self, sender):
        self.filterSheet.close()
        delattr(self, 'filterSheet')

    def processFilter(self, sender):
        argumentsList = self.filterSheet.arguments.get()
        filterName = self.filterSheet.name.get()
        filterDict = {}

        if len(filterName) > 0:
            index = self.filterSheet.importPath.get()
            mode = ['modulePath','fileName'][index]
            filterDict[mode] = importString = self.filterSheet.importPath[index].pathInput.get()

            if len(importString) > 0:
                filterDict['filterObject'] = filterObject = self.filterSheet.filterObject.get()

                if len(filterObject) > 0:

                    for argItem in argumentsList:
                        if argItem.has_key('argument'):
                            key = argItem['argument']
                            if argItem.has_key('value'):
                                value = self.parseValue(argItem['value'])
                                if not filterDict.has_key('arguments'):
                                    filterDict['arguments'] = {}
                                filterDict['arguments'][key] = value
                                if argItem.has_key('min') and argItem.has_key('max'):
                                    try:
                                        mini, maxi = float(argItem['min']), float(argItem['max'])
                                        if not filterDict.has_key('limits'):
                                            filterDict['limits'] = {}
                                        filterDict['limits'][key] = (mini, maxi)
                                    except:
                                        pass

                    if filterName in self.filters:
                        self.filters[filterName] = filterDict
                    elif self.filterSheet.new == False:
                        index = self.w.filtersPanel.filtersList.getSelection()[0]
                        self.filters.changeFilterNameByIndex(index, filterName)
                        self.filters[filterName] = filterDict
                    elif self.filterSheet.new == True:
                        self.filters.addFilter(filterName, filterDict)

                    self.closeFilterSheet(sender)
                    self.updateFiltersList()
                    self.updateOptions()
                    self.updatePreview()

    def addFilter(self, sender):
        self.buildFilterSheet(makeNew=True)
        self.filterSheet.open()

    def removeFilter(self, sender):
        filterName = self.currentFilterKey
        self.filters.removeFilter(filterName)
        self.updateFiltersList()

    def filterSelectionChanged(self, sender):
        selectedFilterName = self.getSelectedFilterName()
        if selectedFilterName in ['Flatten', 'Jitter']:
            self.w.filtersPanel.removeFilter.enable(False)
        else:
            self.w.filtersPanel.removeFilter.enable(True)
        self.cachedFont = RFont(showUI=False)
        self.currentFilterKey = selectedFilterName
        self.updateOptions()
        self.updatePreview()

    def getCurrentFilter(self):
        return self.filters[self.currentFilterKey]

    def getSelectedFilterName(self):
        filtersList = self.w.filtersPanel.filtersList
        filterNamesList = filtersList.get()
        selection = filtersList.getSelection()[0]
        return filterNamesList[selection]

    def switchFillStroke(self, sender):
        self.fill = not self.fill
        displayStates = self.w.preview.getDisplayStates()
        if self.fill == True:
            sender.setTitle('Fill')
            displayStates['Fill'] = True
            displayStates['Stroke'] = False
        elif self.fill == False:
            sender.setTitle('Stroke')
            displayStates['Fill'] = False
            displayStates['Stroke'] = True
        self.w.preview.setDisplayStates(displayStates)

    def parseValue(self, value):
        if isinstance(value, bool):
            value = bool(value)
        elif isinstance(value, (str, unicode)) and value.lower() == 'true':
            value = True
        elif isinstance(value, (str, unicode)) and value.lower() == 'false':
            value = False
        elif value is not '' or value is not None:
            try:
                value = float(value)
            except:
                pass
        return value


    def fontChanged(self, notification):
        self.currentFont = notification['font']
        self.cachedFont = RFont(showUI=False)
        self.updatePreview()

    def end(self, notification):
        self.filters.update()
        for callback, event in self.observers:
            removeObserver(self, event)

PenBallWizard()

if __name__ == '__main__':

    import unittest