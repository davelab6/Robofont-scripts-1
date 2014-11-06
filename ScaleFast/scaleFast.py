#coding=utf-8

'''
v.0.3
ScaleFast is a script with a simple mission:
trying to maintain stem width while you transform a glyph.
To do that, the tool relies on masters (you need at least two),
analyses them and does its best to keep stems consistent
through interpolation, powered by Erik van Blokland’s MutatorMath.

Thanks to Frederik Berlaen for the inspiration (UFOStretch) & consent
'''

from mutatorMath.objects.location import Location
from mutatorMath.objects.mutator import buildMutator
from vanilla import *
from mojo.events import addObserver, removeObserver
from mojo.UI import MultiLineView
from mojo.tools import IntersectGlyphWithLine
from fontMath.mathGlyph import MathGlyph
from defconAppKit.tools.textSplitter import splitText
from AppKit import NSColor, NSBoxCustom, NSDragOperationNone
from math import cos, sin, radians, pi
import re

def fontName(font):
    if isinstance(font, RFont):
        familyName = font.info.familyName
        styleName = font.info.styleName
        if familyName is None:
            familyName = font.info.familyName = 'Unnamed'
        if styleName is None:
            styleName = font.info.styleName = 'Unnamed'
        return ' > '.join([familyName, styleName])
    return ''

def decomposeGlyph(glyph, fixedWidth=False):
    if glyph is not None:
        components = glyph.components
        font = glyph.getParent()
        decomposedGlyph = RGlyph()

        if font is not None:
            for component in components:
                base = font[component.baseGlyph]
                if len(base.components) > 0:
                    base = makePreviewGlyph(base)
                decomponent = RGlyph()
                decomponent.appendGlyph(base)
                decomponent.scale((component.scale[0], component.scale[1]))
                decomponent.move((component.offset[0], component.offset[1]))
                decomposedGlyph.appendGlyph(decomponent)
            for contour in glyph.contours:
                decomposedGlyph.appendContour(contour)

            if fixedWidth:
                decomposedGlyph.width = 1000
                decomposedGlyph.leftMargin = decomposedGlyph.rightMargin = (decomposedGlyph.leftMargin + decomposedGlyph.rightMargin)/2
                decomposedGlyph.scale((.75, .75), (decomposedGlyph.width/2, 0))
                decomposedGlyph.move((0, -50))

            decomposedGlyph.name = glyph.name

        return decomposedGlyph
    return

class ScaleController:

    def __init__(self):
        self.w = Window((800, 500), 'ScaleFast', minSize=(800, 520))
        self.w.controls = Group((15, 15, 250, -15))
        controls = self.w.controls
        allFontsNames = [fontName(font) for font in AllFonts()]
        controls.allfonts = PopUpButton((1, 0, -120, 22), allFontsNames)
        controls.addFont = GradientButton((-105, 0, -65, 22), title='Add', sizeStyle='small', callback=self.addMaster)
        controls.removeFont = GradientButton((-60, 0, -0, 22), title='Remove', sizeStyle='small', callback=self.removeMaster)
        dropSettings = {
            'type':'MyCustomPboardType',
            'operation': NSDragOperationNone,
            'allowDropOnRow':True,
            'callback': self.dropCallback }
        dragSettings = {
            'type':'MyCustomPboardType',
            'operation': NSDragOperationNone,
            'allowDropOnRow':True,
            'callback': self.dragCallback }
        controls.masters = List((0, 30, -0, -345),
            [],
            columnDescriptions= [
                {'title':'font', 'width':155},
                {'title':'vstem', 'editable':True, 'width':40},
                {'title':'hstem', 'editable':True, 'width':40}],
            editCallback=self.updateStems,
            selfDropSettings=dropSettings,
            dragSettings=dragSettings)
        controls.glyphSetTitle = TextBox((0, -122, 70, 22), 'Glyphset', sizeStyle='small')
        controls.glyphSet = ComboBox((70, -125, -0, 22),
            [
            'abcdefghijklmnopqrstuvwxyz',
            'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
            '0123456789',
            '/zero.LP/one.LP/two.LP/three.LP/four.LP/five.LP/six.LP/seven.LP/eight.LP/nine.LP'
            ])
        controls.suffixTitle = TextBox((0, -92, 70, 22), 'Suffix', sizeStyle='small')
        controls.suffix = EditText((70, -95, -0, 22))
        controls.addToTitle = TextBox((0, -62, 70, 22), 'Add to', sizeStyle='small')
        allFontsNames.insert(0, 'New Font')
        controls.addTo = PopUpButton((70, -65, -0, 22), allFontsNames)

        scaleControls = [
            {'name':'width', 'title':'Width', 'unit':'%', 'value':'100.0'},
            {'name':'height', 'title':'Height', 'value':'750'},
            {'name':'stem', 'title':'Stem', 'value':'80'},
            {'name':'shift', 'title':'Shift', 'value':'0'},
            {'name':'tracking', 'title':'Tracking', 'unit':'%', 'value':'0'}
        ]
        controls.scaleGoalsTitle = TextBox((0, -330, -0, 19), 'scale Goals', sizeStyle='small')
        controls.scaleGoalsMode = TextBox((-140, -330, -0, 19), 'Mode: isotropic', sizeStyle='small', alignment='right')
        controls.scaleGoals = Box((0, -310, -0, (len(scaleControls)*30)+10))
        for i, control in enumerate(scaleControls):
            controlName = control['name']
            setattr(controls.scaleGoals, '%s%s'%(controlName, 'Title'), TextBox((10, 8+(i*30), 100, 22), control['title'], sizeStyle='small'))
            if controlName in ['width','shift','tracking']:
                setattr(controls.scaleGoals, controlName, EditText((65, 5+(i*30), 60, 22), control['value'], continuous=False, callback=self.scaleValueInput))
                inputControl = getattr(controls.scaleGoals, controlName)
                inputControl.name = controlName
            elif controlName == 'height':
                setattr(controls.scaleGoals, controlName, ComboBox((65, 5+(i*30), 60, 22), [], callback=self.scaleValueInput))
                inputControl = getattr(controls.scaleGoals, controlName)
                inputControl.name = controlName
            elif controlName == 'stem':
                setattr(controls.scaleGoals, '%s%s'%('v',controlName), ComboBox((65, 5+(i*30), 60, 22), [], callback=self.scaleValueInput))
                setattr(controls.scaleGoals, '%s%s'%('h',controlName), ComboBox((140, 5+(i*30), 60, 22), [], callback=self.scaleValueInput))
                setattr(controls.scaleGoals, 'mode', CheckBox((210, 5+(i*30), -0, 22), u'∞', value=True, callback=self.switchIsotropic, sizeStyle='small'))
                vInputControl = getattr(controls.scaleGoals, '%s%s'%('v',controlName))
                vInputControl.name = '%s%s'%('v',controlName)
                hInputControl = getattr(controls.scaleGoals, '%s%s'%('h',controlName))
                hInputControl.name = '%s%s'%('h',controlName)
                hInputControl.enable(False)
            if controlName == 'shift':
                controls.scaleGoals.shiftUp = SquareButton((140, 7+(i*30), 17, 17), u'⥘', sizeStyle='small', callback=self.scaleValueInput)
                controls.scaleGoals.shiftUp.name = 'shiftUp'
                controls.scaleGoals.shiftDown = SquareButton((160, 7+(i*30), 17, 17), u'⥕', sizeStyle='small', callback=self.scaleValueInput)
                controls.scaleGoals.shiftDown.name = 'shiftDown'
            if controlName == 'height':
                setattr(controls.scaleGoals, 'rel', TextBox((127, 5+(i*30), 15, 22), '/'))
                setattr(controls.scaleGoals, 'refHeight', PopUpButton((140, 5+(i*30), -10, 22), ['capHeight', 'xHeight', 'unitsPerEm'], callback=self.scaleValueInput))
                refHeight = getattr(controls.scaleGoals, 'refHeight')
                refHeight.name = 'refHeight'
            if controlName == 'tracking':
                setattr(controls.scaleGoals, 'trackingAbs', EditText((150, 5+(i*30), 60, 22), control['value'], continuous=False, callback=self.scaleValueInput))
                setattr(controls.scaleGoals, 'trackingAbsUnit', TextBox((215, 10+(i*30), -0, 22), 'upm', sizeStyle='mini'))
                inputControl = getattr(controls.scaleGoals, 'trackingAbs')
                inputControl.name = 'trackingAbs'
            if control.has_key('unit'):
                setattr(controls.scaleGoals, '%s%s'%(controlName, 'Unit'), TextBox((130, 8+(i*30), 40, 22), control['unit'], sizeStyle='small'))
        controls.apply = Button((0, -22, -0, 22), 'Generate glyphSet', callback=self.generateGlyphset)

        self.w.glyphPreview = MultiLineView((280, 30, -0, -0), pointSize=176)
        self.w.glyphPreviewControls = Box((282, 0, -0, 30))
        glyphPreview = self.w.glyphPreview
        previewControls = self.w.glyphPreviewControls
        previewControlsBox = previewControls.getNSBox()
        previewControlsBox.setBoxType_(NSBoxCustom)
        previewControlsBox.setFillColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(.85, .85, .85, 1))
        previewControlsBox.setBorderWidth_(0)
        previewControls.preGlyphInput = EditText((3, 3, 80, 22), callback=self.inputGlyphs)
        previewControls.glyphInput = EditText((86, 3, -166, 22), callback=self.inputGlyphs)
        previewControls.postGlyphInput = EditText((-163, 3, 80, 22), callback=self.inputGlyphs)
        previewControls.preGlyphInput.name = 'pre'
        previewControls.postGlyphInput.name = 'post'
        previewControls.pointSize = ComboBox((-73, 3, -10, 22), [str(p) for p in range(24,256, 8)], callback=self.pointSize)
        previewControls.pointSize.set(176)

        self.scaleControlValues = {'width':1, 'height':1, 'vstem':None, 'hstem':None, 'shift': 0, 'tracking':(1, '%')}
        self.vstemValues = []
        self.hstemValues = []
        self.masters = []
        self.preGlyphList = ''
        self.postGlyphList = ''
        self.glyphList = ''
        self.mode = 'isotropic'
        self.previousMode = None
        self.draggedIndex = None
        self.verticalMetrics = {'descender':-250, 'baseline':0, 'xHeight':500, 'capHeight':750, 'ascender':750}
        self.stickyMetric = 'baseline'
        addObserver(self, 'updateFontList', 'fontDidOpen')
        addObserver(self, 'updateFontList', 'fontWillClose')
        self.w.bind('close', self.windowClose)
        self.w.open()

    def generateGlyphset(self, sender):
        glyphString = self.w.controls.glyphSet.get()
        glyphSet = self.stringToGlyphNames(glyphString)
        if len(glyphSet):
            name, f = self.getSelectedFont(self.w.controls.addTo)
            suffix = glyphString = self.w.controls.suffix.get()
            masters = self.masters
            scaleValues = self.scaleControlValues
            for glyphName in glyphSet:
                scaleedGlyph = self.scaleGlyph(glyphName, masters, scaleValues)
                if scaleedGlyph is not None:
                    f.insertGlyph(scaleedGlyph, glyphName+suffix)
            f.round()
            f.showUI()

    def processGlyphs(self):
        masters = self.masters
        scaleValues = self.scaleControlValues
        stringToGlyphNames = self.stringToGlyphNames
        glyphSet = stringToGlyphNames(self.glyphList)
        if len(masters) > 0:
            baseFont = masters[0]['font']
            preRefGlyph = [baseFont[glyphName] for glyphName in stringToGlyphNames(self.preGlyphList)]
            postRefGlyph = [baseFont[glyphName] for glyphName in stringToGlyphNames(self.postGlyphList)]
            scaleedGlyphLine = []
            if len(masters) > 1 and len(glyphSet):
                for glyphName in glyphSet:
                    scaleedGlyph = self.scaleGlyph(glyphName, masters, scaleValues)
                    if scaleedGlyph is not None:
                        scaleedGlyphLine.append(scaleedGlyph)
            scaleedGlyphLine = preRefGlyph + scaleedGlyphLine + postRefGlyph
            self.w.glyphPreview.set(scaleedGlyphLine)

    def scaleGlyph(self, glyphName, masters, scaleValues):
        width, sc, wishedVStem, wishedHStem, shift, (trackingValue, trackingUnit) = scaleValues['width'], scaleValues['height'], scaleValues['vstem'], scaleValues['hstem'], scaleValues['shift'], scaleValues['tracking']
        mutatorMasters = []
        mode = self.mode
        isValid = self.isValidGlyph(glyphName, [master['font'] for master in masters])

        if isValid:

            if not masters[0].has_key('hstem') and (mode == 'anisotropic'):
                requestedStemLocation = Location(stem=(wishedVStem, wishedHStem))
            elif masters[0].has_key('hstem'):
                requestedStemLocation = Location(vstem=wishedVStem, hstem=wishedHStem)
            else:
                requestedStemLocation = Location(stem=wishedVStem)

            for item in masters:
                masterFont = item['font']
                baseGlyph = masterFont[glyphName]
                masterGlyph = decomposeGlyph(baseGlyph)
                masterGlyph.scale((sc*width, sc))
                masterGlyph.width = baseGlyph.width * sc * width
                try:
                    if trackingUnit == '%':
                        masterGlyph.angledLeftMargin *= trackingValue
                        masterGlyph.angledRightMargin *= trackingValue
                    elif trackingUnit == 'upm':
                        masterGlyph.angledLeftMargin += trackingValue
                        masterGlyph.angledRightMargin += trackingValue
                except:
                    if trackingUnit == '%':
                        masterGlyph.leftMargin *= trackingValue
                        masterGlyph.rightMargin *= trackingValue
                    elif trackingUnit == 'upm':
                        masterGlyph.leftMargin += trackingValue
                        masterGlyph.rightMargin += trackingValue
                italicAngle = masterFont.info.italicAngle
                if italicAngle is not None:
                    xShift = shift * cos(radians(-italicAngle)+pi/2)
                    yShift = shift * sin(radians(-italicAngle)+pi/2)
                elif italicAngle is None:
                    xShift, yShift = 0, shift
                masterGlyph.move((xShift, yShift))
                if item.has_key('hstem') and (mode == 'anisotropic'):
                    axis = {'stem':item['vstem']*sc*width}
                elif item.has_key('hstem') and (mode == 'bidimensionnal'):
                    axis = {'vstem':item['vstem']*sc*width, 'hstem':item['hstem']*sc}
                else:
                    axis = {'stem':item['vstem']*sc*width}
                mutatorMasters.append((Location(**axis), MathGlyph(masterGlyph)))

            return self.getInstance(requestedStemLocation, mutatorMasters)
        return

    def getInstance(self, location, masters):
        b, m = buildMutator(masters)
        if m is not None:
            glyph = m.makeInstance(location).extractGlyph(RGlyph())
            return glyph
        return

    def switchIsotropic(self, sender):
        if len(self.masters):
            b = not bool(sender.get())
            if b == False: self.setMode('isotropic')
            elif b == True: self.setMode('anisotropic')
            self.processGlyphs()
        else:
            sender.set(not sender.get())

    def scaleValueInput(self, sender):
        scaleValueName = sender.name
        if isinstance(sender, (EditText, ComboBox, PopUpButton)):
            value = sender.get()
        if scaleValueName == 'width':
            try: value = float(value)/100.0
            except: value = 1
        elif scaleValueName == 'tracking':
            try: value = (1 + float(value)/100.0, '%')
            except: value = (1, '%')
        elif scaleValueName == 'trackingAbs':
            try: value = (float(value), 'upm')
            except: value = (0, 'upm')
            scaleValueName = 'tracking'
        elif scaleValueName == 'height':
            try:
                refValueIndex = self.w.controls.scaleGoals.refHeight.get()
                refValueName = self.w.controls.scaleGoals.refHeight.getItems()[refValueIndex]
                sourceFont = self.masters[0]['font']
                refValue = getattr(sourceFont.info, refValueName)
                shift = self.scaleControlValues['shift']
                value = float(value)/float(refValue)
            except: value = 1
        elif scaleValueName == 'refHeight':
            try:
                refValueIndex = value
                refValueName = self.w.controls.scaleGoals.refHeight.getItems()[refValueIndex]
                sourceFont = self.masters[0]['font']
                refValue = getattr(sourceFont.info, refValueName)
                heightValue = float(self.w.controls.scaleGoals.height.get())
                value = heightValue/float(refValue)
            except: value = 1
            scaleValueName = 'height'
        elif scaleValueName in ['vstem', 'hstem']:
            try: value = int(value)
            except: value = 80
        elif scaleValueName == 'shift':
            try: value = int(value)
            except: value = 0
        elif scaleValueName == 'shiftUp':
            shift = self.scaleControlValues['shift']
            height = float(self.w.controls.scaleGoals.height.get())
            verticalMetrics = self.verticalMetrics
            value = shift
            for metric in ['xHeight', 'capHeight', 'ascender']:
                if shift < 0:
                    value = 0
                    self.w.controls.scaleGoals.shift.set(str(value))
                    self.stickyMetric = 'baseline'
                    break
                elif shift >= 0:
                    if (shift + height) < verticalMetrics[metric]:
                        value = round(verticalMetrics[metric] - height)
                        self.w.controls.scaleGoals.shift.set(str(value))
                        self.stickyMetric = metric
                        break
                    else:
                        continue
            scaleValueName = 'shift'
        elif scaleValueName == 'shiftDown':
            shift = self.scaleControlValues['shift']
            height = float(self.w.controls.scaleGoals.height.get())
            verticalMetrics = self.verticalMetrics
            value = shift
            for metric in ['ascender', 'capHeight', 'xHeight', 'baseline', 'descender']:
                if shift > verticalMetrics[metric]:
                    value = round(verticalMetrics[metric])
                    self.w.controls.scaleGoals.shift.set(str(value))
                    break
                else:
                    continue
            scaleValueName = 'shift'
        self.scaleControlValues[scaleValueName] = value
        self.processGlyphs()

    def inputGlyphs(self, sender):
        inputString = sender.get()
        if hasattr(sender, 'name'):
            if sender.name == 'pre':
                self.preGlyphList = inputString
            elif sender.name == 'post':
                self.postGlyphList = inputString
        elif not hasattr(sender, 'name'):
            self.glyphList = inputString
        self.processGlyphs()

    def stringToGlyphNames(self, string):
        cmap = self.getCMap()
        if cmap is not None:
            return splitText(string, cmap)
        return []

    def getCMap(self):
        masters = self.masters
        if len(masters):
            sourceFont = masters[0]['font']
            return sourceFont.getCharacterMapping()
        return None

    def pointSize(self, sender):
        value = sender.get()
        try: value = float(value)
        except: value = 72
        self.w.glyphPreview.setPointSize(value)

    def isValidGlyph(self, glyph, fonts):
        isValid = True
        for font in fonts:
            isValid *= glyph in font
            if not isValid: break
        return bool(isValid)

    def approximateVStemWidth(self, font):
        if 'I' in font:
            testGlyph = font['I']
            xMin, yMin, xMax, yMax = testGlyph.box
            hCenter = (yMax - yMin)/2
            i = IntersectGlyphWithLine(testGlyph, ((-200, hCenter), (testGlyph.width+200, hCenter)))
            stemWidth = abs(i[1][0]-i[0][0])
            return int(round(stemWidth))
        return 0

    def approximateHStemWidth(self, font):
        if 'H' in font:
            testGlyph = font['H']
            xMin, yMin, xMax, yMax = testGlyph.box
            vCenter = xMin+(xMax - xMin)/2
            i = IntersectGlyphWithLine(testGlyph, ((vCenter, -500), (vCenter, 1200)))
            stemWidth = abs(i[1][1]-i[0][1])
            return int(round(stemWidth))
        return 0

    def updateStems(self, sender):
        mastersNameAndStem = sender.get()
        if len(mastersNameAndStem):
            inputStemValues = ['%s,%s'%(item['vstem'],item['hstem']) for item in mastersNameAndStem]
            stemValues = self.getStemValues(inputStemValues)
            for i, item in enumerate(stemValues):
                masterFont = self.masters[i]['font']
                self.masters[i] = item
                self.masters[i]['font'] = masterFont
            self.processGlyphs()

    def getStemValues(self, stems):
        previousMode = self.previousMode
        split = self.splitStemValue
        stemValues = [split(stem) for stem in stems]
        keepHStem = self.checkForSecondAxisCondition([item['hstem'] for item in stemValues])
        if (not keepHStem and len(stemValues) > 2) or (len(stemValues) <= 2):
            for stemValue in stemValues: stemValue.pop('hstem', None)
            if (previousMode is not None) and (self.mode not in ['isotropic', 'anisotropic']):
                self.setMode(previousMode)
                self.previousMode = None
            else:
                self.setMode('isotropic')
        else:
            self.setMode('bidimensionnal')
        return stemValues

    def splitStemValue(self, stem):
        s = re.search('(\d+)(,\s?(\d+))?', repr(stem))
        if s:
            if s.group(1) is not None:
                vstem = float(s.group(1))
            else:
                vstem = None
            if s.group(3) is not None:
                hstem = float(s.group(3))
            else:
                hstem = None
            return dict(vstem=vstem, hstem=hstem)
        return 0

    def checkForSecondAxisCondition(self, values):
        if len(values):
            eq = 0
            neq = 0
            l = len(values)
            for i,value in enumerate(values):
                n1value = values[(i+1)%l]
                if n1value == value: eq += 1
                if n1value != value: neq += 1
            return bool(eq) and bool(neq)
        return

    def setMode(self, modeName):
        self.w.controls.scaleGoalsMode.set('Mode: %s'%(modeName))
        if modeName == 'isotropic':
            self.w.controls.scaleGoals.mode.show(True)
            self.w.controls.scaleGoals.mode.set(True)
            self.w.controls.scaleGoals.hstem.set('')
            self.w.controls.scaleGoals.hstem.enable(False)
        elif modeName == 'anisotropic':
            self.w.controls.scaleGoals.mode.show(True)
            self.w.controls.scaleGoals.mode.set(False)
            value = self.w.controls.scaleGoals.vstem.get()
            self.w.controls.scaleGoals.hstem.set(value)
            self.w.controls.scaleGoals.hstem.enable(True)
            self.scaleControlValues['hstem'] = float(value)
        elif modeName == 'bidimensionnal':
            if self.mode == 'isotropic':
                self.previousMode = 'isotropic'
            elif self.mode == 'anisotropic':
                self.previousMode = 'anisotropic'
            self.w.controls.scaleGoals.mode.show(False)
            self.w.controls.scaleGoals.hstem.set(self.hstemValues[0])
            self.w.controls.scaleGoals.hstem.enable(True)
            self.scaleControlValues['hstem'] = self.hstemValues[0]
        self.mode = modeName

    def dropCallback(self, sender, dropInfo):
        if (self.draggedIndex is not None):
            sourceIndex = self.draggedIndex
            destinationIndex = dropInfo['rowIndex']
            mastersList = sender.get()
            masters = self.masters
            if (sourceIndex != 0) and (destinationIndex == 0):
                for itemsList in [mastersList, masters, self.vstemValues, self.hstemValues]:
                    draggedItem = itemsList.pop(sourceIndex)
                    itemsList.insert(0, draggedItem)
                font = masters[0]['font']
                for attribute in ['descender', 'xHeight', 'capHeight', 'ascender']:
                    self.verticalMetrics[attribute] = getattr(font.info, attribute)
                vstem, hstem = self.scaleControlValues['vstem'], self.scaleControlValues['hstem'] = mastersList[0]['vstem'], mastersList[0]['hstem']
                self.w.controls.scaleGoals.vstem.set(vstem)
                self.w.controls.scaleGoals.hstem.set(hstem)
                sender.set(mastersList)

    def dragCallback(self, sender, dropInfo):
        self.draggedIndex = dropInfo[0]

    def addMaster(self, sender):
        controls = self.w.controls
        masterNamesList = controls.masters
        selectedFontName, selectedFont = self.getSelectedFont(self.w.controls.allfonts)
        mastersList = masterNamesList.get()
        namesOnly = [item['font'] for item in mastersList]
        if selectedFontName not in namesOnly:
            vstem = self.approximateVStemWidth(selectedFont)
            hstem = self.approximateHStemWidth(selectedFont)
            mastersList.append({'font':selectedFontName, 'vstem':vstem, 'hstem':hstem})
            self.masters.append({'font':selectedFont, 'vstem':vstem, 'hstem':hstem})
            masterNamesList.set(mastersList)
            self.vstemValues.append(vstem)
            self.hstemValues.append(hstem)
            self.w.controls.scaleGoals.vstem.setItems(self.vstemValues)
            self.w.controls.scaleGoals.hstem.setItems(self.hstemValues)
            if len(mastersList) == 1:
                self.setMainFont(controls, selectedFont, vstem, hstem)
            self.updateStems(masterNamesList)
            self.processGlyphs()

    def removeMaster(self, sender):
        masterNamesList = self.w.controls.masters
        selectedFontName, selectedFont = self.getSelectedFont(self.w.controls.allfonts)
        mastersToRemove = masterNamesList.getSelection()
        mastersList = masterNamesList.get()
        for i in reversed(mastersToRemove):
            vstem = self.approximateVStemWidth(selectedFont)
            hstem = self.approximateHStemWidth(selectedFont)
            mastersList.pop(i)
            self.masters.pop(i)
            self.vstemValues.pop(i)
            self.hstemValues.pop(i)
            self.w.controls.scaleGoals.vstem.setItems(self.vstemValues)
            self.w.controls.scaleGoals.hstem.setItems(self.hstemValues)
        masterNamesList.set(mastersList)
        self.updateStems(masterNamesList)
        self.processGlyphs()

    def setMainFont(self, controls, font, vstem, hstem):
        controls.scaleGoals.vstem.set(vstem)
        controls.scaleGoals.hstem.set(hstem)
        controls.scaleGoals.height.setItems([str(getattr(font.info, height)) for height in ['capHeight', 'xHeight', 'unitsPerEm']])
        controls.scaleGoals.height.set(str(font.info.capHeight))
        self.scaleControlValues['vstem'] = vstem
        self.scaleControlValues['hstem'] = hstem
        for attribute in ['descender', 'xHeight', 'capHeight', 'ascender']:
            self.verticalMetrics[attribute] = getattr(font.info, attribute)

    def getSelectedFont(self, popuplist):
        fontIndex = popuplist.get()
        fontName = popuplist.getItems()[fontIndex]
        if fontName == 'New Font':
            return fontName, RFont(showUI=False)
        else:
            try: return fontName, AllFonts().getFontsByFamilyNameStyleName(*fontName.split(' > '))
            except: return RFont()

    def updateFontList(self, notification):
        notifiedFont = notification['font']
        notifiedFontName = fontName(notifiedFont)
        for fontlist in [self.w.controls.allfonts, self.w.controls.addTo]:
            namesList = fontlist.getItems()
            if notification['notificationName'] == 'fontDidOpen':
                namesList.append(notifiedFontName)
            elif notification['notificationName'] == 'fontWillClose':
                if notifiedFontName in namesList:
                    namesList.remove(notifiedFontName)
                masterList = self.w.controls.masters.get()
                fontsToRemove = []
                for i,item in enumerate(masterList):
                    name = item['font']
                    if name == notifiedFontName:
                        fontsToRemove.append(i)
                for index in fontsToRemove:
                    masterList.pop(i)
                self.w.controls.masters.set(masterList)
            fontlist.setItems(namesList)

    def windowClose(self, notification):
        removeObserver(self, 'fontDidOpen')
        removeObserver(self, 'fontWillClose')

ScaleController()
