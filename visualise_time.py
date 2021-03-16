"""Visualise time containers from annotation."""
from collections import Counter
from typing import List, Dict, Set, Optional, Iterable
from datetime import datetime, timedelta
import re
import json
import sys

import fire
from dateutil.relativedelta import relativedelta
from normtime import normalize
from toposort import toposort_flatten, CircularDependencyError

from entity_types import Id, Document, Entity, Relation
import visualise_rel as vr
from visualise_rel import CLR, DOTHEAD

# TODO: merge visualise_rel.py with this code

# TODO: use dataclass for type annotation in the embedding procedures

# NOTE: relevant time expression parsers/rules are available in timex_modules/

PTN_DATE = re.compile(r"\d\d\d\d-\d\d-\d\d")
PTN_MONTH = re.compile(r"\d\d\d\d-\d\d")
PTN_YEAR = re.compile(r"\d\d\d\d")

TREL_NOT_ON = set(["before", "after", "start", "end"])


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
        # まずは rank constraint なしで time container を cluster subgraph ��して様子見
        output += (
            f"subgraph cluster{ix}{{ rank=same; ordering=out;"
            + "; ".join([f"T{e.id}" for e in container.all_ents()])
            # + "; ".join([f"T{e.id}" for e in container.t_ents])
            + "; }\n"
        )

    output += "}\n"
    return output


class TimeContainer:
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
        if ent.tag == "TIMEX3":
            if "value" in ent.rels_from:
                self.b_ents.add(ent)
            else:
                self.t_ents.add(ent)
        else:
            self.b_ents.add(ent)

    def add_all(self, ents: Iterable[Entity]) -> None:
        for e in ents:
            self.add(e)

    def all_ents(self) -> Set[Entity]:
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
                if ents & other.t_ents:
                    if type_ in ["after", "start"]:
                        return True
        # self <-before- other | self <-end- other
        for t_ent in other.t_ents:
            for type_, ents in t_ent.rels_to.items():
                if ents & self.t_ents:
                    if type_ in ["before", "end"]:
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
        else:
            # no "value" for TIMEX, infer time relations
            # NOTE: based only on two TCs, perfect inference is not possible
            # see sort_tcs()'s latter processing
            for t_ent in self.t_ents:
                for type_, ents in t_ent.rels_to.items():
                    if ents & other.t_ents:
                        if type_ in ["before", "end"]:
                            return True
                        elif type_ in ["after", "start"]:
                            return False
            for t_ent in other.t_ents:
                for type_, ents in t_ent.rels_to.items():
                    if ents & self.t_ents:
                        if type_ in ["before", "end"]:
                            return False
                        elif type_ in ["after", "start"]:
                            return True
            # raise ValueError("Both TimeContainers in comparison must have head TIMEX3.")
            # FIXME: ad-hock operation for List[TC] sorting
            # list.sort() only uses __lt__()
            return False

    def __le__(self, other):
        if self.__lt__(other):
            return True
        else:
            if self.head and other.head:
                dt_self = datetime.fromisoformat(self.head.attrs["value"][:10])
                dt_other = datetime.fromisoformat(other.head.attrs["value"][:10])
                return dt_self <= dt_other
            else:
                raise ValueError(
                    "Both TimeContainers in comparison must have head TIMEX3."
                )

    def __eq__(self, other):
        if self.head and other.head:
            return self.head.attrs["value"][:10] == other.head.attrs["value"][:10]
        else:
            raise ValueError("Both TimeContainers in comparison must have head TIMEX3.")

    def __ne__(self, other):
        return not self.__eq__(other)

    def __ge__(self, other):
        return other.__le__(self)

    def __gt__(self, other):  # self > other
        return other.__lt__(self)


def make_time_containers(entities: List[Entity]) -> List[TimeContainer]:
    """
    time containers = timex clusters connected with 'on'

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

    # print("==BEFORE WHILE==")
    # table: List[List[str]] = []
    # for container in time_containers:
    #     tlist = [container.splittable, container.head] + list(
    #         container.t_ents - set([container.head])
    #     )
    #     table.append([repr(ent) for ent in tlist + list(container.b_ents)])
    # print("\n".join(["\t".join(row) for row in table]))
    # print()
    time_containers = merge_tcs(time_containers)
    # print("==FIRST MERGE==")
    # table = []
    # for container in time_containers:
    #     tlist = [container.splittable, container.head] + list(
    #         container.t_ents - set([container.head])
    #     )
    #     table.append([repr(ent) for ent in tlist + list(container.b_ents)])
    # print("\n".join(["\t".join(row) for row in table]))
    # print()
    while any([tc.splittable for tc in time_containers]):
        # print("INTO WHILE...")
        # print()
        time_containers = [tc_ for tc in time_containers for tc_ in split_tc(tc)]
        time_containers = merge_tcs(time_containers)

        # table = []
        # for container in time_containers:
        #     tlist = [container.splittable, container.head] + list(
        #         container.t_ents - set([container.head])
        #     )
        #     table.append([repr(ent) for ent in tlist + list(container.b_ents)])
        # print("\n".join(["\t".join(row) for row in table]))
        # print()

    time_containers = [tc for tc in time_containers if not is_isolate_tc(tc)]
    sorted_tcs = sort_tcs(time_containers)

    return sorted_tcs


def is_isolate_tc(tc: TimeContainer) -> bool:
    if tc.b_ents:
        return False
    else:
        for t_ent in tc.t_ents:
            if t_ent.rels_to.keys() & TREL_NOT_ON:
                return False
            elif t_ent.rels_from.keys() & TREL_NOT_ON:
                return False
    return True


def make_tc_helper(
    ent: Entity, tc: TimeContainer, to_: bool = True, from_: bool = True
) -> TimeContainer:
    if ent not in tc.all_ents():
        tc.add(ent)
        froms = ent.rels_from.get("on", set()) if from_ else set()
        tos = ent.rels_to.get("on", set()) if to_ else set()
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

    datetimes = [te for te in tc.t_ents if te.attrs["type"] in ["DATE", "TIME"]]
    datedic: Dict[str, List[Entity]] = {}
    for t_ent in datetimes:
        m = PTN_DATE.search(t_ent.attrs["value"])
        if m:  # dismiss all non-ISO date values
            datedic.setdefault(m.group(0), []).append(t_ent)
    durs = [te for te in tc.t_ents if te.attrs["type"] == "DURATION"]

    split_tcs: List[TimeContainer] = []
    if len(datedic.keys()) > 1:  # multi-dates
        for date, t_ents in datedic.items():
            a_tc = TimeContainer()
            for t_ent in t_ents:
                a_tc = make_tc_helper(t_ent, a_tc, to_=False)
            a_tc.fix_normtime_value()
            a_tc.find_head_timex()
            split_tcs.append(a_tc)
        return split_tcs
    elif durs:  # splittable if date-on-duration
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
                        neg=type_ == "end",
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
        else:
            tc.splittable = False
            return [tc]
    else:
        tc.splittable = False
        return [tc]


def parse_duration_value(dur_val: str, date: str = "", neg: bool = False) -> str:
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
    datedic: Dict[str, List[TimeContainer]] = {}
    datedic["UNK"] = []
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

    # # TODO: resolve relative TC's position among absolute TCs
    # Topological sort would solve this!
    relative_tcs = [tc for tc in tcs if not tc.head.attrs["value"]]
    absolute_tcs = [tc for tc in tcs if tc.head.attrs["value"]]
    # rtcs_ix = [f"r{i}" for i in range(len(relative_tcs))]
    atcs_ix = [f"a{i}" for i in range(len(absolute_tcs))]
    g: Dict[str, Set[str]] = {}  # 後 ← 前 の時間関係グラフ
    for ai, ai_ in zip(atcs_ix, atcs_ix[1:]):
        if ai not in g:
            g[ai] = set()
        if ai_ not in g:
            g[ai_] = set()
        g[ai_] |= set([ai])
        g[ai] |= set(
            [
                f"r{i}"
                for i, tc in enumerate(relative_tcs)
                if absolute_tcs[int(ai[1:])].rel_after(tc)
            ]
        )
    for i, rtc in enumerate(relative_tcs):
        if f"r{i}" not in g:
            g[f"r{i}"] = set()
        g[f"r{i}"] |= set(
            [
                f"r{j}"
                for j, tc in enumerate(relative_tcs)
                if i != j and rtc.rel_after(tc)
            ]
        )
        g[f"r{i}"] |= set(
            [
                f"a{j}"
                for j, tc in enumerate(absolute_tcs)
                if i != j and rtc.rel_after(tc)
            ]
        )
    try:
        sorted_ix = toposort_flatten(g)
        sorted_tcs = []
        for ix in sorted_ix:
            if ix[0] == "a":
                sorted_tcs.append(absolute_tcs[int(ix[1:])])
            elif ix[0] == "r":
                sorted_tcs.append(relative_tcs[int(ix[1:])])
        return sorted_tcs
    except CircularDependencyError:
        print("Error: Circular time relations detected.")
        return tcs


def relate_dct(doc: Document) -> None:
    """Convert DCT-Rel to a Relation."""
    assert doc.isbuilt

    # create the DCT entity
    dct = Entity(Id(-1), "TIMEX3", (-2, -1), "DCT", doc=doc)
    dct.attrs["type"] = "DATE"
    doc.entities.insert(0, dct)

    n = len(doc.entities)
    for i in range(n):
        dct_rel = doc.entities[i].attrs.get("DCT-Rel")
        if dct_rel:
            doc.add_relation(dct_rel, doc.entities[i].id, dct.id)


def normalise_all_timex(doc: Document, dct: str) -> None:
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


def to_json(tcs: List[TimeContainer], doc: Document, garbage: bool = True) -> str:
    times = []
    entities = []
    anatomy_ids = []
    embeded_ids = []

    # time and entities
    for tc in tcs:
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
        for b in tc.b_ents:
            if b.tag in ["Change", "Feature"]:
                continue
            elif "value" in b.rels_from:
                # valueはkeyからたどるので取らない
                # TODO: 孤立value?
                continue
            ent = embed_entity(b, tcs, embeded_ids, on_a_tc=tc)
            if "anatomy" in ent:
                # 入れ子regionの親だけとる
                anatomy_ids.append(ent["anatomy"])
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
        # e for e in doc.entities if e.id in anatomy_ids and e.id not in set(embeded_ids)
        e
        for e in doc.entities
        if e.tag in "Anatomical" and e.id not in set(embeded_ids)
    ]
    anatomy = [embed_anatomy(a, embeded_ids) for a in root_anatomicals]

    garbage_ = []
    for doe in doc.entities:
        if doe.id not in embeded_ids:
            # TCに入っておらず，start/end/after/beforeだけついてるentの取り扱い
            ts = infer_timespan(doe, tcs)
            if ts:
                rest_ent = embed_an_entity(doe)
                rest_ent["time"] = ts
                entities.append(rest_ent)
            else:
                # どこにも入ってないものをgarbageにいれる
                garbage_.append(embed_an_entity(doe))

    ret = {
        "entities": entities,
        "times": times,
        "anatomy": anatomy,
        "html": doc.to_html(),
    }
    if garbage:
        ret["garbage"] = garbage_

    return json.dumps(ret, ensure_ascii=False, indent=2)


def find_head_id(id_: Id, tcs: List[TimeContainer]) -> Id:
    for tc in tcs:
        if id_ in [e.id for e in tc.all_ents()]:
            return tc.head.id
    return Id(0)


def is_earlier(tid1, tid2, tcs):
    head_ids = [tc.head.id for tc in tcs]
    ix_tid1 = head_ids.index(tid1)
    ix_tid2 = head_ids.index(tid2)
    return ix_tid1 < ix_tid2


def infer_timespan(e, tcs, on_a_tc=None):
    if not (set(e.rels_to.keys()) & set(Relation.time_rels)):
        return []

    if "start" in e.rels_to and "end" in e.rels_to:
        start_id = find_head_id(list(e.rels_to["start"])[0].id, tcs)
        end_id = find_head_id(list(e.rels_to["end"])[0].id, tcs)
        if is_earlier(start_id, end_id, tcs):
            return [start_id, end_id]

    elif "start" in e.rels_to and "before" in e.rels_to:
        start_id = find_head_id(list(e.rels_to["start"])[0].id, tcs)
        before_id = find_head_id(list(e.rels_to["before"])[0].id, tcs)
        if is_earlier(start_id, before_id, tcs):
            return [start_id, before_id]
        elif on_a_tc:
            # before < start; CORRUPTED
            if is_earlier(start_id, on_a_tc.head.id, tcs):
                # assume "start" is reliable
                return [start_id, on_a_tc.head.id]
            elif is_earlier(on_a_tc.head.id, before_id, tcs):
                # assume "before" is reliable
                return [on_a_tc.head.id, before_id]
        else:
            # assume "start" is reliable
            return [start_id, tcs[-1].head.id]

    elif "end" in e.rels_to and "after" in e.rels_to:
        after_id = find_head_id(list(e.rels_to["after"])[0].id, tcs)
        end_id = find_head_id(list(e.rels_to["end"])[0].id, tcs)
        if is_earlier(after_id, end_id, tcs):
            return [after_id, end_id]
        elif on_a_tc:
            if is_earlier(after_id, on_a_tc.head.id, tcs):
                return [after_id, on_a_tc.head.id]
            if is_earlier(on_a_tc.head.id, end_id, tcs):
                return [on_a_tc.head.id, end_id]
        else:
            return [after_id, tcs[-1].head.id]

    elif "start" in e.rels_to:
        start_id = find_head_id(list(e.rels_to["start"])[0].id, tcs)
        if on_a_tc and is_earlier(start_id, on_a_tc.head.id, tcs):
            return [start_id, on_a_tc.head.id]
        else:
            return [start_id, tcs[-1].head.id]

    elif "end" in e.rels_to:
        end_id = find_head_id(list(e.rels_to["end"])[0].id, tcs)
        if on_a_tc and is_earlier(on_a_tc.head.id, end_id, tcs):
            return [on_a_tc.head.id, end_id]
        else:
            return [tcs[0].head.id, end_id]

    elif "after" in e.rels_to:
        after_id = find_head_id(list(e.rels_to["after"])[0].id, tcs)
        if on_a_tc and is_earlier(after_id, on_a_tc.head.id, tcs):
            return [after_id, on_a_tc.head.id]
        else:
            return [after_id, tcs[-1].head.id]

    elif "before" in e.rels_to:
        before_id = find_head_id(list(e.rels_to["before"])[0].id, tcs)
        if on_a_tc and is_earlier(on_a_tc.head.id, before_id, tcs):
            return [on_a_tc.head.id, before_id]
        else:
            return [tcs[0].head.id, before_id]

    elif "on" in e.rels_to:
        if on_a_tc:
            on_id = on_a_tc.head.id
        else:
            on_id = find_head_id(list(e.rels_to["on"])[0].id, tcs)
        return [on_id, on_id]


def embed_an_entity(e):
    ent = {
        "id": e.id,
        "tag": e.tag,
        "text": e.text,
        "change": [],
        "region": {},
        "value": [],
    }
    if "certainty" in e.attrs:
        ent["certainty"] = e.attrs["certainty"]
    elif "state" in e.attrs:
        ent["state"] = e.attrs["state"]

    return ent


def embed_anatomy(a, embeded_ids):
    anat = {"id": a.id, "text": a.text, "feature": [], "contain": []}
    embeded_ids.append(a.id)

    if "feature" in a.rels_from:
        anat["feature"] = [f.text for f in a.rels_from["feature"]]
        embeded_ids.extend([f.id for f in a.rels_from["feature"]])

    if "region" in a.rels_to:
        anat["contain"] = [
            reg.id for reg in a.rels_to["region"] if reg.tag == "Anatomical"
        ]

    # TODO: if "change" in a.rels_from:

    return anat


def embed_entity(e, tcs, embeded_ids, anat=None, on_a_tc=None):
    ent = embed_an_entity(e)
    embeded_ids.append(e.id)

    ent["time"] = infer_timespan(e, tcs, on_a_tc=on_a_tc)

    if "feature" in e.rels_from:
        ent["feature"] = [f.text for f in e.rels_from["feature"]]
        embeded_ids.extend([f.id for f in e.rels_from["feature"]])
    else:
        ent["feature"] = []

    if anat:
        ent["anatomy"] = anat
    elif "region" in e.rels_from:
        parent = [reg for reg in e.rels_from["region"] if reg.tag == "Anatomical"]
        if parent:
            # FIXME: 複数部位に属する可��性はあるが無視
            ent["anatomy"] = parent.pop().id

    if "region" in e.rels_to:
        for reg in e.rels_to["region"]:
            if "region" in reg.rels_to:
                # E.g. e = "腫瘤", reg = "内部", reg.rels_to["region"] = ["すりガラス影", ...]
                ent["region"][reg.text] = [
                    embed_entity(contained, tcs, embeded_ids, anat=ent.get("anatomy"))
                    for contained in reg.rels_to["region"]
                ]
            else:
                if reg.tag == "Disease":
                    # E.g. e = "腫瘤", reg = "充実部分" => {"充実部分": {<d>充実部分</d>}} (redundant, though)
                    ent["region"][reg.text] = [
                        embed_entity(reg, tcs, embeded_ids, anat=ent.get("anatomy"))
                    ]
                elif reg.tag == "Anatomical":
                    # TODO: ill-defined case
                    # E.g. 腫瘤の内部は著編ありません
                    ent["region"][reg.text] = [embed_anatomy(reg, embeded_ids)]

    if "change" in e.rels_from:
        for cha in e.rels_from["change"]:
            if "compare" in cha.rels_to:
                # FIXME: compareを持たないものは無視する
                # compare先は1個だけのはず…
                comp_to = list(cha.rels_to["compare"])[0]
                if comp_to.tag != "TIMEX3":
                    # FIXME: How to visualise non-time comparison?
                    continue
                comp_to_time = find_head_id(comp_to.id, tcs)
                ent["change"].append({"text": cha.text, "compare": comp_to_time})
                embeded_ids.append(cha.id)
                ent["time"][0] = comp_to_time  # FIXME: compareは前の時点だけ…のはず

    if "value" in e.rels_to:
        for val in e.rels_to["value"]:
            ent["value"].append(embed_an_entity(val))
            embeded_ids.append(val.id)

    return ent


def trace_region(embeded, e_ids):
    e_ids.append(embeded["id"])
    if embeded["region"]:
        containeds = [cont for conts in embeded["region"].values() for cont in conts]
        while containeds:
            e_ids = trace_region(containeds.pop(), e_ids)
    return e_ids


def main(filename_r: str, dct: str, debug: bool = False, dot: bool = False) -> None:
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


if __name__ == "__main__":
    fire.Fire(main)
