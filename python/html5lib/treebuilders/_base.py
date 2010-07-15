from html5lib.constants import scopingElements, tableInsertModeElements, namespaces
try:
    frozenset
except NameError:
    # Import from the sets module for python 2.3
    from sets import Set as set
    from sets import ImmutableSet as frozenset

# The scope markers are inserted when entering object elements,
# marquees, table cells, and table captions, and are used to prevent formatting
# from "leaking" into tables, object elements, and marquees.
Marker = None

class Node(object):
    def __init__(self, name):
        """Node representing an item in the tree.
        name - The tag name associated with the node
        parent - The parent of the current node (or None for the document node)
        value - The value of the current node (applies to text nodes and 
        comments
        attributes - a dict holding name, value pairs for attributes of the node
        childNodes - a list of child nodes of the current node. This must 
        include all elements but not necessarily other node types
        _flags - A list of miscellaneous flags that can be set on the node
        """
        self.name = name
        self.parent = None
        self.value = None
        self.attributes = {}
        self.childNodes = []
        self._flags = []

    def __unicode__(self):
        attributesStr =  " ".join(["%s=\"%s\""%(name, value) 
                                   for name, value in 
                                   self.attributes.iteritems()])
        if attributesStr:
            return "<%s %s>"%(self.name,attributesStr)
        else:
            return "<%s>"%(self.name)

    def __repr__(self):
        return "<%s>" % (self.name)

    def appendChild(self, node):
        """Insert node as a child of the current node
        """
        raise NotImplementedError

    def insertText(self, data, insertBefore=None):
        """Insert data as text in the current node, positioned before the 
        start of node insertBefore or to the end of the node's text.
        """
        raise NotImplementedError

    def insertBefore(self, node, refNode):
        """Insert node as a child of the current node, before refNode in the 
        list of child nodes. Raises ValueError if refNode is not a child of 
        the current node"""
        raise NotImplementedError

    def removeChild(self, node):
        """Remove node from the children of the current node
        """
        raise NotImplementedError

    def reparentChildren(self, newParent):
        """Move all the children of the current node to newParent. 
        This is needed so that trees that don't store text as nodes move the 
        text in the correct way
        """
        #XXX - should this method be made more general?
        for child in self.childNodes:
            newParent.appendChild(child)
        self.childNodes = []

    def cloneNode(self):
        """Return a shallow copy of the current node i.e. a node with the same
        name and attributes but with no parent or child nodes
        """
        raise NotImplementedError


    def hasContent(self):
        """Return true if the node has children or text, false otherwise
        """
        raise NotImplementedError

class TreeBuilder(object):
    """Base treebuilder implementation
    documentClass - the class to use for the bottommost node of a document
    elementClass - the class to use for HTML Elements
    commentClass - the class to use for comments
    doctypeClass - the class to use for doctypes
    """

    #Document class
    documentClass = None

    #The class to use for creating a node
    elementClass = None

    #The class to use for creating comments
    commentClass = None

    #The class to use for creating doctypes
    doctypeClass = None
    
    #Fragment class
    fragmentClass = None

    def __init__(self, namespaceHTMLElements):
        if namespaceHTMLElements:
            self.defaultNamespace = "http://www.w3.org/1999/xhtml"
        else:
            self.defaultNamespace = None
        self.reset()
    
    def reset(self):
        self.openElements = []
        self.activeFormattingElements = []

        #XXX - rename these to headElement, formElement
        self.headPointer = None
        self.formPointer = None

        self.insertFromTable = False

        self.document = self.documentClass()

    def elementInScope(self, target, variant=None):
        # Exit early when possible.
        listElementsMap = {
            None:scopingElements,
            "button":scopingElements | set([(namespaces["html"], "button")]),
            "list":scopingElements | set([(namespaces["html"], "ol"),
                                          (namespaces["html"], "ul")]),
            "table":set([(namespaces["html"], "html"),
                         (namespaces["html"], "table")])
            }
        listElements = listElementsMap[variant]

        for node in reversed(self.openElements):
            if node.name == target:
                return True
            elif node.nameTuple in listElements:
                return False

        assert False # We should never reach this point

    def reconstructActiveFormattingElements(self):
        # Within this algorithm the order of steps described in the
        # specification is not quite the same as the order of steps in the
        # code. It should still do the same though.

        # Step 1: stop the algorithm when there's nothing to do.
        if not self.activeFormattingElements:
            return

        # Step 2 and step 3: we start with the last element. So i is -1.
        i = len(self.activeFormattingElements) - 1
        entry = self.activeFormattingElements[i]
        if entry == Marker or entry in self.openElements:
            return

        # Step 6
        while entry != Marker and entry not in self.openElements:
            if i == 0:
                #This will be reset to 0 below
                i = -1
                break
            i -= 1
            # Step 5: let entry be one earlier in the list.
            entry = self.activeFormattingElements[i]

        while True:
            # Step 7
            i += 1

            # Step 8
            entry = self.activeFormattingElements[i]
            clone = entry.cloneNode() #Mainly to get a new copy of the attributes

            # Step 9
            element = self.insertElement({"type":"StartTag", 
                                          "name":clone.name, 
                                          "namespace":clone.namespace, 
                                          "data":clone.attributes})

            # Step 10
            self.activeFormattingElements[i] = element

            # Step 11
            if element == self.activeFormattingElements[-1]:
                break

    def clearActiveFormattingElements(self):
        entry = self.activeFormattingElements.pop()
        while self.activeFormattingElements and entry != Marker:
            entry = self.activeFormattingElements.pop()

    def elementInActiveFormattingElements(self, name):
        """Check if an element exists between the end of the active
        formatting elements and the last marker. If it does, return it, else
        return false"""

        for item in self.activeFormattingElements[::-1]:
            # Check for Marker first because if it's a Marker it doesn't have a
            # name attribute.
            if item == Marker:
                break
            elif item.name == name:
                return item
        return False

    def insertRoot(self, token):
        element = self.createElement(token)
        self.openElements.append(element)
        self.document.appendChild(element)

    def insertDoctype(self, token):
        name = token["name"]
        publicId = token["publicId"]
        systemId = token["systemId"]

        doctype = self.doctypeClass(name, publicId, systemId)
        self.document.appendChild(doctype)

    def insertComment(self, token, parent=None):
        if parent is None:
            parent = self.openElements[-1]
        parent.appendChild(self.commentClass(token["data"]))
                           
    def createElement(self, token):
        """Create an element but don't insert it anywhere"""
        name = token["name"]
        namespace = token.get("namespace", self.defaultNamespace)
        element = self.elementClass(name, namespace)
        element.attributes = token["data"]
        return element

    def _getInsertFromTable(self):
        return self._insertFromTable

    def _setInsertFromTable(self, value):
        """Switch the function used to insert an element from the
        normal one to the misnested table one and back again"""
        self._insertFromTable = value
        if value:
            self.insertElement = self.insertElementTable
        else:
            self.insertElement = self.insertElementNormal

    insertFromTable = property(_getInsertFromTable, _setInsertFromTable)
        
    def insertElementNormal(self, token):
        name = token["name"]
        namespace = token.get("namespace", self.defaultNamespace)
        element = self.elementClass(name, namespace)
        element.attributes = token["data"]
        self.openElements[-1].appendChild(element)
        self.openElements.append(element)
        return element

    def insertElementTable(self, token):
        """Create an element and insert it into the tree""" 
        element = self.createElement(token)
        if self.openElements[-1].name not in tableInsertModeElements:
            return self.insertElementNormal(token)
        else:
            #We should be in the InTable mode. This means we want to do
            #special magic element rearranging
            parent, insertBefore = self.getTableMisnestedNodePosition()
            if insertBefore is None:
                parent.appendChild(element)
            else:
                parent.insertBefore(element, insertBefore)
            self.openElements.append(element)
        return element

    def insertText(self, data, parent=None):
        """Insert text data."""
        if parent is None:
            parent = self.openElements[-1]

        if (not self.insertFromTable or (self.insertFromTable and
                                         self.openElements[-1].name 
                                         not in tableInsertModeElements)):
            parent.insertText(data)
        else:
            # We should be in the InTable mode. This means we want to do
            # special magic element rearranging
            parent, insertBefore = self.getTableMisnestedNodePosition()
            parent.insertText(data, insertBefore)
            
    def getTableMisnestedNodePosition(self):
        """Get the foster parent element, and sibling to insert before
        (or None) when inserting a misnested table node"""
        # The foster parent element is the one which comes before the most
        # recently opened table element
        # XXX - this is really inelegant
        lastTable=None
        fosterParent = None
        insertBefore = None
        for elm in self.openElements[::-1]:
            if elm.name == "table":
                lastTable = elm
                break
        if lastTable:
            # XXX - we should really check that this parent is actually a
            # node here
            if lastTable.parent:
                fosterParent = lastTable.parent
                insertBefore = lastTable
            else:
                fosterParent = self.openElements[
                    self.openElements.index(lastTable) - 1]
        else:
            fosterParent = self.openElements[0]
        return fosterParent, insertBefore

    def generateImpliedEndTags(self, exclude=None):
        name = self.openElements[-1].name
        # XXX td, th and tr are not actually needed
        if (name in frozenset(("dd", "dt", "li", "option", "optgroup", "p", "rp", "rt"))
            and name != exclude):
            self.openElements.pop()
            # XXX This is not entirely what the specification says. We should
            # investigate it more closely.
            self.generateImpliedEndTags(exclude)

    def getDocument(self):
        "Return the final tree"
        return self.document
    
    def getFragment(self):
        "Return the final fragment"
        #assert self.innerHTML
        fragment = self.fragmentClass()
        self.openElements[0].reparentChildren(fragment)
        return fragment

    def testSerializer(self, node):
        """Serialize the subtree of node in the format required by unit tests
        node - the node from which to start serializing"""
        raise NotImplementedError
