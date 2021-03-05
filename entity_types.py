"""Classes for brat annotation entities and a whole document."""
from __future__ import annotations
import sys
from typing import List, Dict, Tuple, NewType, TypeVar, Set
from pathlib import Path
from xml.sax import xmlreader, saxutils
import io

Id = NewType("Id", int)
A = TypeVar("A")

# TODO: one source of truth
# TODO: xml string parsing
# TODO: xml output with original texts

BRAT2HTML = {
    "Disease": "disease",
    "Anatomical": "anatomical",
    "Feature": "feature",
    "Change": "change",
    "TIMEX3": "TIMEX3",
    "TestTest": "testtest",
    "TestKey": "testkey",
    "TestVal": "testval",
    "MedicineKey": "medkey",
    "MedicineVal": "medval",
    "ClinicalContext": "cc",
    "Remedy": "remedy",
    "Pending": "pending",
}


class Relation:
    """Struct of a relation."""

    time_rels = ["on", "before", "after", "start", "finish", "omit"]
    basic_rels = ["change", "compare", "feature", "region", "value", "pending"]

    def __init__(self, _id: Id, name: str, arg1: Id, arg2: Id):
        self.id = _id
        self.name = name
        self.arg1 = arg1
        self.arg2 = arg2

    @classmethod
    def from_raw(cls, raw_line: str) -> Relation:
        _id, raw_rel = raw_line.split("\t")
        name, arg1, arg2 = raw_rel.split(" ")
        return cls(
            _id=Id(int(_id[1:])),
            name=name,
            arg1=Id(int(arg1.split(":T")[1])),
            arg2=Id(int(arg2.split(":T")[1])),
        )

    def __repr__(self):
        return f"<R{self.id} {self.name} {self.arg1}->{self.arg2}>"

    def __str__(self):
        return f"R{self.id}\t{self.name} Arg1:T{self.arg1} Arg2:T{self.arg2}"

    def __hash__(self):
        return hash((self.name, self.arg1, self.arg2))

    def __eq__(self, other):
        _name = self.name == other.name
        _arg1 = self.arg1 == other.arg1
        _arg2 = self.arg2 == other.arg2
        return all([_name, _arg1, _arg2])


class Attribute:
    """Struct for an attribute"""

    def __init__(self, _id: Id, name: str, target: Id, value: str):
        self.id = _id
        self.name = name
        self.target = target
        self.value = value

    @classmethod
    def from_raw(cls, raw_line: str) -> Attribute:
        _id, raw_attr = raw_line.split("\t")
        name, target, value = raw_attr.split(" ")
        return cls(
            _id=Id(int(_id[1:])), name=name, target=Id(int(target[1:])), value=value
        )

    def __repr__(self):
        return f"<A{self.id} T{self.target}.{self.name}={self.value}>"

    def __str__(self):
        return f"A{self.id}\t{self.name} T{self.target} {self.value}"

    def __hash__(self):
        return hash((self.name, self.target, self.value))

    def __eq__(self, other):
        _name = self.name == other.name
        _target = self.target == other.target
        _value = self.value == other.value
        return all([_name, _target, _value])


class Other:
    """Struct for other ann lines"""

    def __init__(self, *cols: str):
        self.cols = cols
        self.id = Id(int(cols[0][1:]))

    @classmethod
    def from_raw(cls, raw_line: str) -> Other:
        cols = raw_line.split("\t")
        return cls(*cols)

    def __repr__(self):
        return f"<{self.cols}>"

    def __str__(self):
        return "\t".join(self.cols)


class Entity:
    """Struct of an entity."""

    excl_time = ["Anatomical", "Feature", "Pending"]

    def __init__(
        self, _id: Id, tag: str, span: Tuple[int, int], text: str, doc: Document = None
    ):
        self.id = _id
        self.tag = tag
        self.span = span
        self.text = text

        # self._attrs: Dict[str, Attribute] = {}
        # self._rels_to: Dict[str, Set[Relation]] = {}
        # self._rels_from: Dict[str, Set[Relation]] = {}

        # # dictやset にすることで uniqueness を保つ
        self.attrs: Dict[str, str] = {}
        self.rels_to: Dict[str, Set[Entity]] = {}
        self.rels_from: Dict[str, Set[Entity]] = {}

        self.others: List[Other] = []

        self.parent_doc = doc

    def __hash__(self):
        return hash((self.tag, *self.span, self.text))

    def __eq__(self, other):
        _tag = self.tag == other.tag
        _span = self.span == other.span
        _text = self.text == other.text
        return all([_tag, _span, _text])

    @classmethod
    def from_raw(cls, raw_line: str) -> Entity:
        _id, raw_span, text = raw_line.split("\t")
        tag, begin, end = raw_span.split(" ")
        return cls(
            _id=Id(int(_id[1:])),
            tag=tag,
            span=(int(begin), int(end)),
            text=text,
        )

    def __repr__(self):
        """Print concise information for debug."""
        if "certainty" in self.attrs:
            c = self.attrs["certainty"]
            if c == "positive":
                cert = "+"
            elif c == "negative":
                cert = "-"
            elif c == "suspicious":
                cert = "?"
            elif c == "general":
                cert = "*"
            return f"<T{self.id} {self.tag}({cert}) {self.text}>"
        elif "state" in self.attrs:
            s = self.attrs["state"]
            if s == "executed":
                state = "+"
            elif s == "negated":
                state = "-"
            elif s == "scheduled":
                state = "?"
            elif s == "other":
                state = "*"
            return f"<T{self.id} {self.tag}({state}) {self.text}>"
        elif "type" in self.attrs:
            if "value" in self.attrs:
                return f"<T{self.id} {self.tag}({self.attrs['type'][:3]}) {self.text} ({self.attrs['value']})>"
            else:
                return f"<T{self.id} {self.tag}({self.attrs['type'][:3]}) {self.text}>"
        else:
            return f"<T{self.id} {self.tag} {self.text}>"

    def __str__(self):
        """Convert to Brat annotation format."""
        return f"T{self.id}\t{self.tag} {self.span[0]} {self.span[1]}\t{self.text}"

    def set_attribute(self, attrname: str, attrval: str) -> None:
        # NOTE: For reactive operation to relations and attributes, the objects Relation and Attribute are directly stored.
        self.attrs[attrname] = attrval
        self.parent_doc.update_needed = True

    # def set_relation_to(self, relation: Relation) -> None:
    #     """self.id == relation.arg1"""
    #     self.rels_to.setdefault(relation.name, set()).add(relation)
    def set_relation_to(self, reltype: str, entity: Entity) -> None:
        self.rels_to.setdefault(reltype, set()).add(entity)
        self.parent_doc.update_needed = True

    # def set_relation_from(self, relation: Relation) -> None:
    #     """self.id == relation.arg2"""
    #     self.rels_from.setdefault(relation.name, set()).add(relation)
    def set_relation_from(self, reltype: str, entity: Entity) -> None:
        self.rels_from.setdefault(reltype, set()).add(entity)
        self.parent_doc.update_needed = True

    def set_other(self, other: Other) -> None:
        self.others.append(other)
        self.parent_doc.update_needed = True


class Document:
    """Store of all annotations."""

    def __init__(self, filename: str):
        self.entities: List[Entity] = []
        self.attributes: List[Attribute] = []
        self.relations: List[Relation] = []
        self.others: List[Other] = []

        # store maximum IDs
        self.ent_id_max = 0
        self.attr_id_max = 0
        self.rel_id_max = 0
        self.other_id_max = 0

        # states
        self.isbuilt = False  # True == initialised
        self.update_needed = False
        # if True, there is relation/attribute updates, implying the need for update to self.relations/attributes

        p = Path(filename)
        if p.suffix == ".ann":
            with open(p, "r") as fi:
                for line in fi:
                    self._read_ann_line(line.strip())
            with open(p.with_suffix(".txt"), "r") as ftxt:
                self.txt = ftxt.read()
        else:
            raise ValueError("Specify BRAT .ann file.")

        self._build_doc()

    def _read_ann_line(self, line: str) -> None:
        assert self.isbuilt is False

        if line.startswith("T"):
            self.entities.append(Entity.from_raw(line))
        elif line.startswith("A"):
            self.attributes.append(Attribute.from_raw(line))
        elif line.startswith("R"):
            self.relations.append(Relation.from_raw(line))
        else:
            self.others.append(Other.from_raw(line))

    def _build_doc(self):
        """Update entities with attributes and relations."""
        assert self.isbuilt is False

        for ent in self.entities:
            self.ent_id_max = max(self.ent_id_max, ent.id)
            ent.parent_doc = self

        for attr in self.attributes:
            self.attr_id_max = max(self.attr_id_max, attr.id)
            e = self.findby_id(attr.target)
            e.set_attribute(attr.name, attr.value)

        for rel in self.relations:
            self.rel_id_max = max(self.rel_id_max, rel.id)
            e1 = self.findby_id(rel.arg1)
            e2 = self.findby_id(rel.arg2)
            e1.set_relation_to(rel.name, e2)
            e2.set_relation_from(rel.name, e1)

        for other in self.others:
            self.other_id_max = max(self.other_id_max, other.id)
            e = self.findby_id(rel.arg1)
            e.set_other(other)

        self.isbuilt = True
        self.update_needed = False

    def findby_id(self, _id: Id) -> Entity:
        """Find an entity specified by the ID"""
        es = [e for e in self.entities if e.id == _id]
        assert len(es) == 1, "Non-unique IDs are stored in the doc!"
        return es[0]

    def _validate(self) -> None:
        assert self.isbuilt is True, "Not initialised yet"
        # assert self.update_needed is False, "update_doc() required"

    def sortedby_occurrence(self, tgt_anno: str = "entities") -> None:
        self._validate()

        setattr(
            self, tgt_anno, sorted(getattr(self, tgt_anno), key=lambda e: e.span[0])
        )

    def update_attribute(self, attrtype: str, target: Id, value: str) -> None:
        self._validate()

        e = self.findby_id(target)
        if attrtype in e.attrs and not self.update_needed:
            # find an existing Attribute
            attr = [
                a for a in self.attributes if a.name == attrtype and a.target == target
            ][0]
            attr.value = value
        else:
            self.attr_id_max += 1
            new_attr = Attribute(
                _id=Id(self.attr_id_max), name=attrtype, target=target, value=value
            )
            e.set_attribute(attrtype, value)
            self.attributes.append(new_attr)

    def add_relation(self, reltype: str, arg1: Id, arg2: Id) -> None:
        self._validate()

        e1 = self.findby_id(arg1)
        e2 = self.findby_id(arg2)
        if e2 not in e1.rels_to.get(reltype, []):
            # No 'update' for rel. Just 'add' a new one
            self.rel_id_max += 1
            new_rel = Relation(
                _id=Id(self.rel_id_max), name=reltype, arg1=arg1, arg2=arg2
            )
            e1.set_relation_to(reltype, e2)
            e2.set_relation_from(reltype, e1)
            self.relations.append(new_rel)
        elif self.update_needed:
            # No 'update' for rel. Just 'add' a new one
            self.rel_id_max += 1
            new_rel = Relation(
                _id=Id(self.rel_id_max), name=reltype, arg1=arg1, arg2=arg2
            )
            self.relations.append(new_rel)

    def _update_doc(self) -> None:
        # TODO: implement a more efficient update procedure
        # reset all lists accodring to the current state of each Entity
        self.attributes = []
        self.attr_id_max = 0
        self.relations = []
        self.rel_id_max = 0
        for e in self.entities:
            for attrtype, attrval in e.attrs.items():
                self.update_attribute(attrtype, e.id, attrval)
            for reltype, rels in e.rels_to.items():
                for rel in rels:
                    self.add_relation(reltype, e.id, rel.id)

        self.attr_id_max = max(*[a.id for a in self.attributes])
        self.rel_id_max = max(*[r.id for r in self.relations])
        self.update_needed = False

    def update_doc(self) -> None:
        assert self.isbuilt is True
        if self.update_needed:
            self._update_doc()

    def output_ann(self, fout=sys.stdout):
        self.update_doc()

        # sort lists by IDs　just in case
        self.entities = sorted(self.entities, key=lambda e: e.id)
        # self.attributes = sorted(self.attributes, key=lambda a: a.id)
        # self.relations = sorted(self.relations, key=lambda r: r.id)

        # print
        annotations: List[list] = [
            self.entities,
            self.relations,
            self.attributes,
            self.others,
        ]
        for anno in annotations:
            for a in anno:
                if a is not None:
                    print(a, file=fout)

    def to_html(self, standalone: bool = False) -> str:
        # dismiss all "relation" info; only output NEs
        if standalone:
            # return a complete html
            raise NotImplementedError

        self.sortedby_occurrence()
        ents = self.entities[:]  # shallow copy

        output = io.StringIO()
        attr_doc = xmlreader.AttributesImpl({"class": "ner-doc"})
        xmldoc = saxutils.XMLGenerator(output, encoding="UTF-8")
        # xmldoc.startDocument()  # => <?xml version...>
        xmldoc.startElement("div", attr_doc)  # => <div>
        cursor = 0
        while ents:
            ent = ents.pop(0)
            if ent.id < 0 or ent.span[0] < 0:  # some special entities like DCT
                continue

            if cursor < ent.span[0]:
                xmldoc.characters(self.txt[cursor : ent.span[0]])
            attr = xmlreader.AttributesImpl(self._attrdict(ent))
            xmldoc.startElement("span", attr)
            assert self.txt[ent.span[0] : ent.span[1]] == ent.text
            xmldoc.characters(ent.text)
            xmldoc.endElement("span")
            cursor = ent.span[1]

        if cursor < len(self.txt) - 1:
            xmldoc.characters(self.txt[cursor:-1])

        xmldoc.endElement("div")  # => </body>
        # xmldoc.endDocument()  # => kinda .close()
        html = output.getvalue()
        html = html.replace("\n", "<br>")
        output.close()  # clear memory

        return html

    def _attrdict(self, ent: Entity) -> Dict[str, str]:
        if "certainty" in ent.attrs:
            htmlclass = f"{BRAT2HTML[ent.tag]}-{ent.attrs['certainty']}"
        elif "state" in ent.attrs:
            htmlclass = f"{BRAT2HTML[ent.tag]}-{ent.attrs['state']}"
        else:
            htmlclass = f"{BRAT2HTML[ent.tag]}"

        return {"id": f"T{ent.id}", "class": htmlclass}
