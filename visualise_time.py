"""Visualise time containers from annotation."""

import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Set, Union

import fire
from dateutil.relativedelta import relativedelta
from normtime import normalize
from toposort import CircularDependencyError, toposort_flatten

import visualise_rel as vr
from entity_types import Document, Entity, Id, Relation
from visualise_rel import CLR, DOTHEAD

# Python 3.9+ implements TopologicalSorter in graphlib


# TODO: merge visualise_rel.py with this code

# TODO: use dataclass for type annotation in the embedding procedures

# NOTE: relevant time expression parsers/rules are available in timex_modules/

PTN_DATE = re.compile(r"\d\d\d\d-\d\d-\d\d")
PTN_MONTH = re.compile(r"\d\d\d\d-\d\d")
PTN_YEAR = re.compile(r"\d\d\d\d")

LIT_on = "timeOn"
LIT_before = "timeBefore"
LIT_after = "timeAfter"
LIT_begin = "timeStart"
LIT_end = "timeEnd"
TREL_NOT_ON = {LIT_on, LIT_before, LIT_after, LIT_begin, LIT_end}


def generate_dot(doc: Document) -> str:
    """Draw a chronologically aligned dot graph."""
    # output = DOTHEAD
    output = "digraph G {rankdir=LR; newrank=true; node [shape=box,style=filled,fontname=Helvetica]"
    entities = doc.entities
    # entities = [e for e in doc.entities if e.tag == "TIMEX3"]
    # ids = [e.id for e in entities]
    # Define all nodes first
    for ent in entities:
        if ent.id == Id(-1):
            ent.id = Id(10000)
        label = vr._make_dot_label(ent)
        output += f'T{ent.id}  [label="{label}",fillcolor="{CLR[ent.tag]}"];\n'
    for rel in doc.relations:
        if rel.name in rel.basic_rels:
            output += f'T{rel.arg1} -> T{rel.arg2} [label="{rel.name}"];\n'
        # if rel.arg1 in ids and rel.arg2 in ids:
        if rel.name in rel.time_rels and not rel.name.startswith("o"):
            # NOTE: dirty hack for negative id nodes (DCT, in our case)
            if rel.arg1 == Id(-1):
                rel.arg1 = Id(10000)
            if rel.arg2 == Id(-1):
                rel.arg2 = Id(10000)
            output += f'T{rel.arg1} -> T{rel.arg2} [label="{rel.name}",color="magenta",fontcolor="magenta"];\n'

    # create time containers
    containers = make_time_containers([e for e in doc.entities if e.tag == "TIMEX3"])

    # define the timeline
    # FIXME: chronological ordering
    output += "{ "
    output += " -> ".join([f"T{container.head.id}" for container in containers])
    output += " [arrowhead=none] }\n"

    for ix, container in enumerate(containers):
        # TODO: 全部をrank=sameのsubgraphにするときっと一列になる
        # まずは rank constraint なしで time container を cluster subgraph して様子見
        output += (
            f"subgraph cluster{ix}{{ rank=same; ordering=out;"
            + "; ".join([f"T{e.id}" for e in container.all_ents()])
            # + "; ".join([f"T{e.id}" for e in container.t_ents])
            + "; }\n"
        )

    output += "}\n"
    return output


class TimeContainer:
    """Time container to store the entities occuring at the same time."""

    def __init__(self, ents: Optional[List[Entity]] = None):
        self.b_ents: Set[Entity] = set()
        self.t_ents: Set[Entity] = set()
        self.splittable = False
        # splittable if:
        # - multi dates inside
        # - date-on-duration inside
        self.head: Entity = None

        if ents:
            self.add_all(ents)

    def __repr__(self):
        return f"<TC head={repr(self.head)[1:-1]}>"

    def add(self, ent: Entity) -> None:
        """Add an entity.

        Args:
            ent (Entity): an entity to add.
        """
        if ent.tag == "TIMEX3":
            if "value" in ent.rels_from:
                self.b_ents.add(ent)
            else:
                self.t_ents.add(ent)
        else:
            self.b_ents.add(ent)

    def add_all(self, ents: Iterable[Entity]) -> None:
        """Add multiple entities at once.

        Args:
            ents (Iterable[Entity]): entities to add
        """
        for e in ents:
            self.add(e)

    def all_ents(self) -> Set[Entity]:
        """Return all entities inside.

        Returns:
            Set[Entity]: a set of entities contained
        """
        return self.t_ents | self.b_ents

    def fix_normtime_value(self) -> None:
        """if time and date exists, update time's date to date's date."""
        dates = [timex for timex in self.t_ents if timex.attrs["type"] == "DATE"]
        dateset: Set[str] = set()
        for date in dates:
            m = PTN_DATE.search(date.attrs["value"])
            if m:
                dateset.add(m.group(0))
            elif PTN_MONTH.match(date.attrs["value"]):
                date.attrs["value"] += "-01"
                dateset.add(date.attrs["value"])
            elif PTN_YEAR.match(date.attrs["value"]):
                date.attrs["value"] += "-01-01"
                dateset.add(date.attrs["value"])
        times = [timex for timex in self.t_ents if timex.attrs["type"] == "TIME"]

        if len(dateset) > 1:
            # give up if all dates are not the same date
            self.splittable = True  # split later by split_tc()
            return None
        elif len(dateset) == 1:
            if [timex for timex in self.t_ents if timex.attrs["type"] == "DURATION"]:
                self.splittable = True
                return None
            # update time's value
            the_date = dateset.pop()
            for time in times:
                d, t = time.attrs["value"].split("T")
                time.attrs["value"] = f"{the_date}T{t}"
        else:
            return None

    def find_head_timex(self) -> None:
        """Find and set the 'head' TIMEX3 entity

        Raises:
            ValueError: if no timex3 entities inside
        """
        datetimes = [t for t in self.t_ents if t.attrs["type"] in ["DATE", "TIME"]]
        if datetimes:
            for dt in datetimes:
                m = PTN_DATE.match(dt.attrs["value"])
                if m:
                    # splittableは外の関数で考慮するのでここではfirst oneで良い
                    self.head = dt
                    break
            # fallback if no absolute dates or times
            if self.head is None:
                self.head = datetimes[0]
        else:  # fallback
            if self.t_ents:
                self.head = list(self.t_ents)[0]
            else:
                raise ValueError(f"No TIMEX inside: {self.all_ents()}")

    def rel_after(self, other):
        """Return True if `self` happened after `other`, accodring to time relations only."""
        # self -after-> other | self -start-> other
        for t_ent in self.t_ents:
            for type_, ents in t_ent.rels_to.items():
                if ents & other.t_ents and type_ in [LIT_after, LIT_begin]:
                    return True
        # self <-before- other | self <-finish- other
        for t_ent in other.t_ents:
            for type_, ents in t_ent.rels_to.items():
                if ents & self.t_ents and type_ in [LIT_before, LIT_end]:
                    return True
        return False

    def rel_before(self, other):
        """Return True if `self` happened before `other`, accodring to time relations only."""
        # self -before-> other | self -finish-> other
        for t_ent in self.t_ents:
            for type_, ents in t_ent.rels_to.items():
                if ents & other.t_ents and type_ in [LIT_before, LIT_end]:
                    return True
        # self <-after- other | self <-start- other
        for t_ent in other.t_ents:
            for type_, ents in t_ent.rels_to.items():
                if ents & self.t_ents and type_ in [LIT_after, LIT_begin]:
                    return True
        return False

    def __lt__(self, other):  # self < other
        m_date_self = PTN_DATE.search(self.head.attrs["value"])
        m_date_other = PTN_DATE.search(other.head.attrs["value"])
        if m_date_self and m_date_other:
            try:
                dt_self = datetime.fromisoformat(m_date_self.group(0))
                dt_other = datetime.fromisoformat(m_date_other.group(0))
            except:
                print(self.head, file=sys.stderr)
                print(repr(m_date_self), file=sys.stderr)
                print(repr(m_date_other), file=sys.stderr)
                raise
            return dt_self < dt_other
        # ELSE: no "value" for TIMEX, infer time relations
        # NOTE: based only on two TCs, perfect inference is not possible
        # see sort_tcs()'s latter processing
        for t_ent in self.t_ents:
            for type_, ents in t_ent.rels_to.items():
                if ents & other.t_ents:
                    if type_ in [LIT_before, LIT_end]:
                        return True
                    if type_ in [LIT_after, LIT_begin]:
                        return False
        for t_ent in other.t_ents:
            for type_, ents in t_ent.rels_to.items():
                if ents & self.t_ents:
                    if type_ in [LIT_before, LIT_end]:
                        return False
                    if type_ in [LIT_after, LIT_begin]:
                        return True
        # raise ValueError("Both TimeContainers in comparison must have head TIMEX3.")
        # FIXME: ad-hock operation for List[TC] sorting
        # list.sort() only uses __lt__()
        return False

    def __le__(self, other):
        if self.__lt__(other):
            return True
        if self.head and other.head:
            dt_self = datetime.fromisoformat(self.head.attrs["value"][:10])
            dt_other = datetime.fromisoformat(other.head.attrs["value"][:10])
            return dt_self <= dt_other
        raise ValueError("Both TimeContainers in comparison must have head TIMEX3.")

    def __eq__(self, other):
        if self.head and other.head:
            return self.head.attrs["value"][:10] == other.head.attrs["value"][:10]
        raise ValueError("Both TimeContainers in comparison must have head TIMEX3.")

    def __ne__(self, other):
        return not self.__eq__(other)

    def __ge__(self, other):
        return other.__le__(self)

    def __gt__(self, other):  # self > other
        return other.__lt__(self)


def _tc_debug_printer(section, tcs):
    print(section, file=sys.stderr)
    table: List[List[str]] = []
    for container in tcs:
        tlist = [container.splittable, container.head] + list(
            container.t_ents - {container.head}
        )

        table.append([repr(ent) for ent in tlist + list(container.b_ents)])
    print("\n".join(["\t".join(row) for row in table]), file=sys.stderr)
    print(file=sys.stderr)


def make_time_containers(entities: List[Entity]) -> List[TimeContainer]:
    """Analyse all entities in a document to generate time containers.

    time containers = timex clusters connected with 'on'

    Steps:
    - make absolute time expressions parent of time containers
    - order time containers chronologically
    """
    # recursively find the root → recursively find all on-related
    time_containers: List[TimeContainer] = []
    while entities:
        ent = entities.pop(0)
        # debug = debugger.Pdb().set_trace()
        tc = TimeContainer()
        tc = make_tc_helper(ent, tc)
        tc.fix_normtime_value()
        tc.find_head_timex()
        time_containers.append(tc)
        entities = [entity for entity in entities if entity not in tc.all_ents()]

    # _tc_debug_printer("==BEFORE WHILE==", time_containers)
    time_containers = merge_tcs(time_containers)
    # _tc_debug_printer("==FIRST MERGE==", time_containers)
    while any(tc.splittable for tc in time_containers):
        time_containers = [tc_ for tc in time_containers for tc_ in split_tc(tc)]
        time_containers = merge_tcs(time_containers)

        # _tc_debug_printer("==INSIDE WHILE==", time_containers)

    # _tc_debug_printer("==AFTER WHILE==", time_containers)
    time_containers = [tc for tc in time_containers if not is_isolate_tc(tc)]
    # _tc_debug_printer("==REMOVE ISOLATED==", time_containers)
    sorted_tcs = sort_tcs(time_containers)
    # _tc_debug_printer("==SORTED==", sorted_tcs)

    return sorted_tcs


def is_isolate_tc(tc: TimeContainer) -> bool:
    """Check if this time container is isolated or not."""
    if tc.b_ents:
        return False
    for t_ent in tc.t_ents:
        if t_ent.rels_to.keys() & TREL_NOT_ON:
            return False
        if t_ent.rels_from.keys() & TREL_NOT_ON:
            return False
    return True


def make_tc_helper(
    ent: Entity, tc: TimeContainer, to_: bool = True, from_: bool = True
) -> TimeContainer:
    """Recursive function to create a time container.

    Traverse all 'related' entities of the input entity
    to include them into a given time container.

    Args:
        ent (Entity): an entity to process.
        tc (TimeContainer): a time container of focus.
        to_ (bool, optional): whether to process rels_to. Defaults to True.
        from_ (bool, optional): whether to process rels_from. Defaults to True.

    Returns:
        TimeContainer: updated `tc`
    """
    if ent not in tc.all_ents():
        tc.add(ent)
        froms = ent.rels_from.get(LIT_on, set()) if from_ else set()
        tos = ent.rels_to.get(LIT_on, set()) if to_ else set()
        rel_ents = froms | tos
        while rel_ents:
            rel_ent = rel_ents.pop()
            tc = make_tc_helper(rel_ent, tc, to_=to_, from_=from_)

    return tc


def split_tc(tc: TimeContainer) -> List[TimeContainer]:
    """Split erronuously contained different-date TCs."""
    tc.fix_normtime_value()
    if not tc.splittable:
        return [tc]
    split_tcs: List[TimeContainer] = []

    # if different dates are contained in this `tc`,
    # then split it per each date
    datetimes = [te for te in tc.t_ents if te.attrs["type"] in ["DATE", "TIME"]]
    datedic: Dict[str, List[Entity]] = {}
    for t_ent in datetimes:
        m = PTN_DATE.search(t_ent.attrs["value"])
        if m:  # dismiss all non-ISO date values
            datedic.setdefault(m.group(0), []).append(t_ent)
    if len(datedic.keys()) > 1:  # multi-dates
        for t_ents in datedic.values():
            a_tc = TimeContainer()
            for t_ent in t_ents:
                a_tc = make_tc_helper(t_ent, a_tc, to_=False)
            a_tc.fix_normtime_value()
            a_tc.find_head_timex()
            split_tcs.append(a_tc)
        return split_tcs

    # splittable if date-on-duration
    durs = [te for te in tc.t_ents if te.attrs["type"] == "DURATION"]
    if durs:
        for dur in durs:
            for type_, tos in dur.rels_to.items():
                dur_on_to = tc.t_ents & tos
                if dur_on_to:
                    for dot in dur_on_to:
                        m = PTN_DATE.search(dot.attrs["value"])
                        if m:
                            the_date = dot.attrs["value"]
                            break
                    a_tc = TimeContainer()
                    a_tc = make_tc_helper(dur, a_tc, to_=False)
                    dur_date_val = parse_duration_value(
                        dur.attrs["value"],
                        date=the_date,
                        neg=type_ == LIT_end,
                    )
                    dur_date = Entity(
                        Id(dur.id + 10000), "TIMEX3", (-2, -1), dur_date_val
                    )
                    dur_date.attrs["type"] = "DATE"
                    dur_date.attrs["value"] = dur_date_val
                    a_tc.add(dur_date)
                    a_tc.head = dur_date
                    split_tcs.append(a_tc)
        if split_tcs:
            all_other = [split_tc.all_ents() for split_tc in split_tcs]
            if all_other:
                rest_tc = TimeContainer()
                rest_tc.add_all(tc.all_ents() - set.union(*all_other))
                rest_tc.fix_normtime_value()
                rest_tc.find_head_timex()
                split_tcs.append(rest_tc)
            return split_tcs
        # else:
        tc.splittable = False
        return [tc]
    # else:
    tc.splittable = False
    return [tc]


def parse_duration_value(dur_val: str, date: str = "", neg: bool = False) -> str:
    """Parse [TIMEX3 type=duration]'s normalised value.

    Since Timex3[dur] has the length of the duration only,
    we have no idea about when this duration locates in a 'date' level.
    This function tries to give the start or end date of the given timex3[dur].

    Args:
        dur_val (str): the time value of a timex3[dur]
        date (str, optional): an associated date. Defaults to "".
        neg (bool, optional): give True if the duration occurred before the date.
                                Defaults to False.

    Returns:
        str: ISO formatted date value
    """
    if date:
        the_date = datetime.fromisoformat(date)
    else:  # FIXME
        the_date = datetime.today()

    if dur_val.startswith("PT"):  # time
        if dur_val.endswith("M"):  # minutes
            m = re.search(r"PT(\d+)M", dur_val)
            if m:
                if neg:
                    the_date = the_date - timedelta(minutes=int(m.group(1)))
                else:
                    the_date = the_date + timedelta(minutes=int(m.group(1)))
    elif dur_val.startswith("P"):
        if dur_val.endswith("Y"):  # years
            m = re.search(r"P(\d+)Y", dur_val)
            if m:
                if neg:
                    the_date = the_date - relativedelta(years=int(m.group(1)))
                else:
                    the_date = the_date + relativedelta(years=int(m.group(1)))
        elif dur_val.endswith("M"):  # months
            m = re.search(r"P(\d+)M", dur_val)
            if m:
                if neg:
                    the_date = the_date - relativedelta(months=int(m.group(1)))
                else:
                    the_date = the_date + relativedelta(months=int(m.group(1)))
        elif dur_val.endswith("W"):  # weeks
            m = re.search(r"P(\d+)W", dur_val)
            if m:
                if neg:
                    the_date = the_date - relativedelta(weeks=int(m.group(1)))
                else:
                    the_date = the_date + relativedelta(weeks=int(m.group(1)))
        elif dur_val.endswith("D"):  # days
            m = re.search(r"P(\d+)D", dur_val)
            if m:
                if neg:
                    the_date = the_date - timedelta(days=int(m.group(1)))
                else:
                    the_date = the_date + timedelta(days=int(m.group(1)))

    return the_date.isoformat(timespec="seconds")


def merge_tcs(tcs: List[TimeContainer]) -> List[TimeContainer]:
    """Merge same-date TCs."""
    datedic: Dict[str, List[TimeContainer]] = {"UNK": []}
    for tc in tcs:
        try:
            m = PTN_DATE.search(tc.head.attrs["value"])
        except:
            print(tc.all_ents(), file=sys.stderr)
            raise
        if m:
            datedic.setdefault(m.group(0), []).append(tc)
        else:
            datedic["UNK"].append(tc)

    new_tcs = []
    for date, tcs_ in datedic.items():
        if date == "UNK":
            new_tcs += tcs_
            continue

        if len(tcs_) > 1:
            merged_tc = TimeContainer(ents=[e for tc in tcs_ for e in tc.all_ents()])
            merged_tc.fix_normtime_value()
            merged_tc.find_head_timex()
            new_tcs.append(merged_tc)
        else:
            new_tcs.append(tcs_.pop())

    return new_tcs


def sort_tcs(tcs: List[TimeContainer]) -> List[TimeContainer]:
    """Sort time containers.

    Assume normalised time values available.
    """
    # sort by head as much as possible -> sortable, unsortable
    # try to infer time relations container-wise
    for tc in tcs:
        tc.find_head_timex()  # just in case

    # __lt__() based sorting is imperfect for empty value timex
    tcs.sort()
    # _tc_debug_printer("==SIMPLE SORT==", tcs)

    # resolve relative TC's position among absolute TCs
    # Topological sort would solve this!
    relative_tcs = [tc for tc in tcs if not tc.head.attrs["value"]]
    absolute_tcs = [tc for tc in tcs if tc.head.attrs["value"]]
    # rtcs_ix = [f"r{i}" for i in range(len(relative_tcs))]
    atcs_ix = [f"a{i}" for i in range(len(absolute_tcs))]
    g: Dict[str, Set[str]] = {ai: set() for ai in atcs_ix}  # 後 ← 前 の時間関係グラフ
    if len(atcs_ix) > 1:
        for ai, ai_ in zip(atcs_ix, atcs_ix[1:]):
            g[ai_] |= {ai}
            g[ai] |= {
                f"r{i}"
                for i, tc in enumerate(relative_tcs)
                if absolute_tcs[int(ai[1:])].rel_after(tc)
            }

            g[ai_] |= {
                f"r{i}"
                for i, tc in enumerate(relative_tcs)
                if absolute_tcs[int(ai_[1:])].rel_after(tc)
            }

    elif len(atcs_ix) == 1:
        g["a0"] |= {
            f"r{i}"
            for i, tc in enumerate(relative_tcs)
            if absolute_tcs[0].rel_after(tc)
        }

    for i, rtc in enumerate(relative_tcs):
        if f"r{i}" not in g:
            g[f"r{i}"] = set()
        g[f"r{i}"] |= {
            f"r{j}" for j, tc in enumerate(relative_tcs) if i != j and rtc.rel_after(tc)
        }

        g[f"r{i}"] |= {
            f"a{j}" for j, tc in enumerate(absolute_tcs) if rtc.rel_after(tc)
        }

    try:
        # print(g, file=sys.stderr)
        sorted_ix = toposort_flatten(g)
        # print(sorted_ix, file=sys.stderr)
        sorted_tcs = []
        for ix in sorted_ix:
            if ix[0] == "a":
                sorted_tcs.append(absolute_tcs[int(ix[1:])])
            elif ix[0] == "r":
                sorted_tcs.append(relative_tcs[int(ix[1:])])
        return sorted_tcs
    except CircularDependencyError:
        print("WARNING: Circular time relations detected.", file=sys.stderr)
        return tcs


def relate_dct(doc: Document) -> None:
    """Convert DCT-Rel to a Relation."""
    assert doc.isbuilt

    # create the DCT entity
    dct = Entity(
        Id(-1), "TIMEX3", (-2, -1), "DCT", doc=doc
    )  # values are incompatible with brat
    # dct = Entity(
    #     Id(5001), "TIMEX3", (0, 2), "##", doc=doc
    # )  # for iaa calculation (ad-hoc)
    dct.attrs["type"] = "DATE"
    doc.entities.insert(0, dct)

    n = len(doc.entities)
    for i in range(n):
        dct_rel = doc.entities[i].attrs.get("DCT-Rel")
        if dct_rel:
            doc.add_relation(dct_rel, doc.entities[i].id, dct.id)


def normalise_all_timex(doc: Document, dct: str) -> None:
    """Normalise all timex3 entities in a document.

    Args:
        doc (Document): the document to process
        dct (str): document creation time
    """
    for entity in doc.entities:
        if entity.tag != "TIMEX3":
            continue
        if entity.id == -1:  # DCT
            entity.attrs["value"] = dct
        else:
            entity.attrs["value"] = normalize(
                entity.text, TYPE=entity.attrs["type"], dct=dct
            )
            # the return of `normalize` follows TimeL's 'value' spec


def toposort_region_value(ents: Iterable[Entity]) -> List[Entity]:
    """Topologically sort subRegion and keyValue relations.

    Args:
        ents (Iterable[Entity]): entities to sort

    Returns:
        List[Entity]: sorted entities
    """
    g: Dict[Id, Set[Id]] = {ent.id: set() for ent in ents}
    for ent in ents:
        if "region" in ent.rels_from:
            g[ent.id] |= {reg.id for reg in ent.rels_from["region"]}
        if "value" in ent.rels_from:
            g[ent.id] |= {val.id for val in ent.rels_from["value"]}
    try:
        sorted_ids = toposort_flatten(g)
    except CircularDependencyError:
        print("WARNING: Circular basic relations detected.", file=sys.stderr)
        return ents
    sorted_ents = []
    for sorted_id in sorted_ids:
        search = [ent for ent in ents if ent.id == sorted_id]
        if search:
            sorted_ents.append(search[0])
    return sorted_ents


def to_json(
    tcs: List[TimeContainer], doc: Document, garbage: bool = True, obj=False
) -> Union[str, dict]:
    """Convert time containers to JSON.

    Args:
        tcs (List[TimeContainer]): time containers
        doc (Document): a document to process
        garbage (bool, optional): set True if garbage entities needed in the output.
                                    Defaults to True.
        obj (bool, optional): set True to get a Dict object.

    Returns:
        str: JSON string
        dict: a JSON (dict) object if `obj`=True
    """
    times = []
    entities = []
    embeded_ids = []

    # embed head-timex and contained entities
    for tc in tcs:
        # embed head-timex
        if PTN_DATE.match(tc.head.attrs["value"]):
            date_val = tc.head.attrs["value"]
        else:
            date_val = ""
        times.append(
            {
                "id": tc.head.id,
                "text": tc.head.text,
                "value": date_val,
                "type": tc.head.attrs["type"],
            }
        )
        embeded_ids.extend([t.id for t in tc.t_ents])

        # embed contained entities
        bents = toposort_region_value(tc.b_ents)
        # for b in tc.b_ents:
        while bents:
            b = bents.pop(0)
            if b.id in embeded_ids:
                continue
            if b.tag in ["Change", "Feature"]:
                continue
            ent = embed_entity(b, tcs, embeded_ids, on_a_tc=tc)
            entities.append(ent)

    # print(json.dumps(entities, ensure_ascii=False, indent=2))
    # de-duplicate top-level entities
    c = Counter(embeded_ids)
    dup_ids = [k for k, v in c.items() if v > 1]
    entities = [entity for entity in entities if entity["id"] not in dup_ids]

    # Anatomy
    # FIXME: all anotomy, anyway
    # TODO: anatomy包含関係 knowledge-based
    root_anatomicals = [
        e for e in doc.entities if e.tag in "Anatomical" and e.id not in embeded_ids
    ]
    anatomy = [embed_anatomy(a, embeded_ids) for a in root_anatomicals]

    garbage_ = []
    for doe in doc.entities:
        if doe.id not in embeded_ids:
            if doe.tag in ["Change", "Feature"]:
                garbage_.append(embed_garbage(doe))
            else:
                # TCに入っておらず，start/end/after/beforeだけついてるentの取り扱い
                ts = infer_timespan(doe, tcs)
                if ts:
                    # FIXME: Disease ← anatomy, feature, ...
                    rest_ent = embed_entity(doe, tcs, embeded_ids)
                    rest_ent["time"] = ts
                    entities.append(rest_ent)
                else:
                    # どこにも入ってないものをgarbageにいれる
                    garbage_.append(embed_garbage(doe))

    ret = {
        "entities": entities,
        "times": times,
        "anatomy": anatomy,
        "html": doc.to_html(),
    }
    if garbage:
        ret["garbage"] = garbage_

    return ret if obj else json.dumps(ret, ensure_ascii=False, indent=2)


def find_head_id(id_: Id, tcs: List[TimeContainer]) -> Id:
    """Find the head entity's ID of a TC to which the input ID belongs
    among the given TCs

    Args:
        id_ (Id): an ID to query.
        tcs (List[TimeContainer]): TCs to search for.

    Returns:
        Id: the head entity's ID.
            return 0 if no match.
    """
    for tc in tcs:
        if id_ in [e.id for e in tc.all_ents()]:
            return tc.head.id
    return Id(0)


def is_earlier(tid1, tid2, tcs):
    """Helper function to judge which timex is earlier."""
    head_ids = [tc.head.id for tc in tcs]
    ix_tid1 = head_ids.index(tid1)
    ix_tid2 = head_ids.index(tid2)
    return ix_tid1 < ix_tid2


def infer_timespan(e, tcs, on_a_tc=None):
    """Infer an exact chronological span of an entity as much as possible."""
    if not (set(e.rels_to.keys()) & set(Relation.time_rels)):
        return []

    if LIT_begin in e.rels_to and LIT_end in e.rels_to:
        start_id = find_head_id(list(e.rels_to[LIT_begin])[0].id, tcs)
        end_id = find_head_id(list(e.rels_to[LIT_end])[0].id, tcs)
        if is_earlier(start_id, end_id, tcs):
            return [start_id, end_id]

    elif LIT_begin in e.rels_to and LIT_before in e.rels_to:
        start_id = find_head_id(list(e.rels_to[LIT_begin])[0].id, tcs)
        before_id = find_head_id(list(e.rels_to[LIT_before])[0].id, tcs)
        if is_earlier(start_id, before_id, tcs):
            return [start_id, before_id]
        if on_a_tc:
            # before < start; CORRUPTED
            if is_earlier(start_id, on_a_tc.head.id, tcs):
                # assume LIT_begin is reliable
                return [start_id, on_a_tc.head.id]
            if is_earlier(on_a_tc.head.id, before_id, tcs):
                # assume LIT_before is reliable
                return [on_a_tc.head.id, before_id]
        # else:
        # assume LIT_begin is reliable
        return [start_id, tcs[-1].head.id]

    elif LIT_end in e.rels_to and LIT_after in e.rels_to:
        after_id = find_head_id(list(e.rels_to[LIT_after])[0].id, tcs)
        end_id = find_head_id(list(e.rels_to[LIT_end])[0].id, tcs)
        if is_earlier(after_id, end_id, tcs):
            return [after_id, end_id]
        elif on_a_tc:
            if is_earlier(after_id, on_a_tc.head.id, tcs):
                return [after_id, on_a_tc.head.id]
            if is_earlier(on_a_tc.head.id, end_id, tcs):
                return [on_a_tc.head.id, end_id]
        else:
            return [after_id, tcs[-1].head.id]

    elif LIT_begin in e.rels_to:
        start_id = find_head_id(list(e.rels_to[LIT_begin])[0].id, tcs)
        if on_a_tc and is_earlier(start_id, on_a_tc.head.id, tcs):
            return [start_id, on_a_tc.head.id]
        else:
            return [start_id, tcs[-1].head.id]

    elif LIT_end in e.rels_to:
        end_id = find_head_id(list(e.rels_to[LIT_end])[0].id, tcs)
        if on_a_tc and is_earlier(on_a_tc.head.id, end_id, tcs):
            return [on_a_tc.head.id, end_id]
        else:
            return [tcs[0].head.id, end_id]

    elif LIT_after in e.rels_to:
        after_id = find_head_id(list(e.rels_to[LIT_after])[0].id, tcs)
        if on_a_tc and is_earlier(after_id, on_a_tc.head.id, tcs):
            return [after_id, on_a_tc.head.id]
        else:
            return [after_id, tcs[-1].head.id]

    elif LIT_before in e.rels_to:
        before_id = find_head_id(list(e.rels_to[LIT_before])[0].id, tcs)
        if on_a_tc and is_earlier(on_a_tc.head.id, before_id, tcs):
            return [on_a_tc.head.id, before_id]
        else:
            return [tcs[0].head.id, before_id]

    elif LIT_on in e.rels_to:
        if on_a_tc:
            on_id = on_a_tc.head.id
        else:
            on_id = find_head_id(list(e.rels_to[LIT_on])[0].id, tcs)
        return [on_id, on_id]


def embed_anatomy(a, embeded_ids):
    """Embed an anatomy entity into JSON."""
    anat = {"id": a.id, "text": a.text, "feature": [], "contain": []}
    embeded_ids.append(a.id)

    anat["feature"] = embed_feature(a, embeded_ids)
    if "change" in a.rels_from:
        # TODO: how to deal with compare_to?
        anat["change"] = [{"text": cha.text} for cha in a.rels_from["change"]]
        embeded_ids.extend([cha.id for cha in a.rels_from["change"]])

    if "region" in a.rels_to:
        anat["contain"] = [
            reg.id for reg in a.rels_to["region"] if reg.tag == "Anatomical"
        ]

    return anat


def embed_feature(e, embeded_ids):
    """Embed a feature entity into JSON."""
    if "feature" in e.rels_from:
        embeded_ids.extend([f.id for f in e.rels_from["feature"]])
        return [f.text for f in e.rels_from["feature"]]
    else:
        return []


def embed_change(e, embeded_ids, tcs):
    """Embed a change entity into JSON."""
    changes = []
    if "change" in e.rels_from:
        for cha in e.rels_from["change"]:
            if "compare" in cha.rels_to:
                # compare先は1個だけのはず…
                comp_to = list(cha.rels_to["compare"])[0]
                if comp_to.tag != "TIMEX3":
                    # FIXME: How to visualise non-time comparison?
                    continue
                comp_to_time = find_head_id(comp_to.id, tcs)
                changes.append({"text": cha.text, "compare": comp_to_time})
            else:
                changes.append({"text": cha.text})
            embeded_ids.append(cha.id)
    return changes


def embed_entity_init(e, embeded_ids):
    """Common initialisation of an JSON-embeded entity."""
    ent = {
        "id": e.id,
        "tag": e.tag,
        "text": e.text,
        "change": [],
        "feature": [],
        "region": {},
        "value": [],
    }
    if "certainty" in e.attrs:
        ent["certainty"] = e.attrs["certainty"]
    elif "state" in e.attrs:
        ent["state"] = e.attrs["state"]

    embeded_ids.append(e.id)
    return ent


def embed_entity(e, tcs, embeded_ids, on_a_tc=None, anat=None):
    """Embed an entity into JSON."""
    # Assume topologically sorted by region and value

    ent = embed_entity_init(e, embeded_ids)
    # even if recursive call holds e.tag == "Anatomical", still embed it as `entity`

    if anat:
        ent["anatomy"] = anat
    elif "region" in e.rels_from:
        parent = [reg for reg in e.rels_from["region"] if reg.tag == "Anatomical"]
        if parent:
            # FIXME: 複数部位に属する可能性はあるが無視
            ent["anatomy"] = parent.pop().id

    ent["time"] = infer_timespan(e, tcs, on_a_tc=on_a_tc)

    ent["feature"] = embed_feature(e, embeded_ids)

    ent["change"] = embed_change(e, embeded_ids, tcs)
    comp_tos = [comp_to["compare"] for comp_to in ent["change"] if "compare" in comp_to]
    if comp_tos:
        tcids = [tc.head.id for tc in tcs]
        # take the earliest changeRef-ed time
        ent["time"][0] = [tcid for tcid in tcids if tcid in comp_tos][0]

    if "value" in e.rels_to:
        for val in e.rels_to["value"]:
            ent["value"].append(embed_entity(val, tcs, embeded_ids, on_a_tc=on_a_tc))

    if "region" in e.rels_to:
        for reg in e.rels_to["region"]:
            if "region" in reg.rels_to:
                # E.g. e = "腫瘤", reg = "内部", reg.rels_to["region"] = ["すりガラス影", ...]
                # TODO: reg自身に付与されたfeatureやchangeを表現できない
                ent["region"][reg.text] = [
                    embed_entity(contained, tcs, embeded_ids, anat=ent.get("anatomy"))
                    for contained in reg.rels_to["region"]
                ]
                embeded_ids.append(reg.id)
            else:
                if reg.tag == "Disease":
                    # E.g. e = "腫瘤", reg = "充実部分" => {"充実部分": {<d>充実部分</d>}} (redundant, though)
                    ent["region"][reg.text] = [
                        embed_entity(reg, tcs, embeded_ids, anat=ent.get("anatomy"))
                    ]
                elif reg.tag == "Anatomical":
                    # TODO: ill-defined case
                    # E.g. 腫瘤の内部は著変ありません
                    ent["region"][reg.text] = [embed_anatomy(reg, embeded_ids)]

    return ent


def embed_garbage(e):
    """Embed an entity that is not rendered in a timeline output (garbage)."""
    return {
        "id": e.id,
        "tag": e.tag,
        "text": e.text,
        "rels_to": {
            type_: [(relto.id, relto.tag, relto.text) for relto in reltos]
            for type_, reltos in e.rels_to.items()
        },
        "rels_from": {
            type_: [(relfr.id, relfr.tag, relfr.text) for relfr in relfrs]
            for type_, relfrs in e.rels_from.items()
        },
    }


def trace_region(embeded, e_ids):
    """Trace subRegion relations."""
    e_ids.append(embeded["id"])
    if embeded["region"]:
        containeds = [cont for conts in embeded["region"].values() for cont in conts]
        while containeds:
            e_ids = trace_region(containeds.pop(), e_ids)
    return e_ids


def main_lib(doc, dct=None):
    """MAIN for being called from library."""
    relate_dct(doc)
    if not dct:
        dct = date.today().isoformat()
    normalise_all_timex(doc, dct)
    containers = make_time_containers([e for e in doc.entities if e.tag == "TIMEX3"])
    return to_json(containers, doc, obj=True)


def main(filename_r, dct, debug=False, dot=False, repl=False):
    """MAIN.

    Args:
        filename_r (str): a `recover_omit`-ed ANN file path.
        dct (str): the document creation time.
        debug (bool, optional): True if debug info is needed. Defaults to False.
                                raw Time Container tables will output in stdout.
        dot (bool, optional): set True to output DOT format text.
                                Defaults to False, i.e. JSON for HeaRT is default.
        repl (bool, optional): set True to investigate processed objects with python-fire.
                                Defaults to False.

    Returns:
        Tuple[Document, List[containers]]: only if repl=True.
    """
    doc = Document(filename_r)
    relate_dct(doc)
    normalise_all_timex(doc, dct)
    containers = make_time_containers([e for e in doc.entities if e.tag == "TIMEX3"])

    if debug:
        table: List[List[str]] = []
        contained_ids: List[Id] = []
        for container in containers:
            contained_ids += [e.id for e in container.all_ents()]
            tlist = [container.head] + list(container.t_ents - set([container.head]))
            table.append([repr(ent) for ent in tlist + list(container.b_ents)])
        table.append(
            [repr(entity) for entity in doc.entities if entity.id not in contained_ids]
        )
        print("\n".join(["\t".join([str(i)] + row) for i, row in enumerate(table)]))
    else:
        if dot:
            print(generate_dot(doc))
        else:
            print(to_json(containers, doc))

    if repl:
        return (doc, containers)


if __name__ == "__main__":
    fire.Fire(main)
