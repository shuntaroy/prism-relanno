"""Recover omit relations from an annotated result.

original.ann -> recovered.ann
"""
import shutil

# import time
import sys
from pathlib import Path

import fire

from entity_types import Document, Id
from visualise_time import relate_dct

# def debug_print(*obj):
#     print(*obj)
#     time.sleep(1)
DCT_ID = -1


def recover_on(doc: Document) -> None:
    """Recover 'on'-relationship.

    Assume `entities` are sorted by the occurence order.
    """
    on_scope: Id = Id(0)  # on省略の対象となるTIMEXのid
    for e in doc.entities:
        if e.tag != "TIMEX3":
            # debug_print("looking at:", e)
            # debug_print("  on_scope =", on_scope)
            if "DCT-Rel" in e.attrs:
                dct_rel = e.attrs["DCT-Rel"]
            else:
                dct_rel = None
            has_on = "on" in e.rels_to

            # debug_print("  has_on =", has_on, "| has_dct_on =", has_dct_on)
            if dct_rel == "on":
                # update on_scope to DCT regardless of whether e has on-rel
                on_scope = Id(DCT_ID)  # the special value for DCT
                # debug_print("  update on_scope -> -1")
            else:
                if has_on:
                    # update on_scope
                    on_to_ids = [on.id for on in e.rels_to["on"]]
                    on_to_timexes = [doc.findby_id(on_to_id) for on_to_id in on_to_ids]
                    # take the first occurence
                    on_scope = sorted(on_to_timexes, key=lambda t: t.span[0])[0].id
                    # debug_print("  update on_scope ->", doc.findby_id(on_scope))
                else:
                    # recover omit on-rel
                    if (on_scope != 0) and (e.tag not in e.excl_time):
                        has_time = any(
                            [
                                e.rels_to.get(trel)
                                for trel in ["before", "after", "start", "finish"]
                            ]
                        ) or bool(dct_rel)
                        # debug_print("  has_time =", has_time)
                        is_gen = e.attrs.get("certainty") == "general"
                        is_oth = e.attrs.get("state") == "other"
                        if not has_time and not (is_gen or is_oth):
                            # on-rel is not needed if e has other time rels
                            if on_scope == DCT_ID:  # == DCT
                                doc.update_attribute("DCT-Rel", e.id, "on")
                                # debug_print("  update DCT-Rel -> on")
                            else:
                                doc.add_relation("on", e.id, on_scope)
                                # debug_print("  add on-rel ->", doc.findby_id(on_scope))
    # doc.update_doc()


def recover_value(doc: Document) -> None:
    """Recover 'value'-relationship.

    Explicitly draw 'value' relationships between key-value 1:1 occurences.
    Assume `entities` are sorted by the occurence order.
    """
    for i, j in zip(range(len(doc.entities)), range(1, len(doc.entities))):
        i_is_key = doc.entities[i].tag.endswith("Key")
        j_is_val = doc.entities[j].tag == doc.entities[i].tag.replace("Key", "Val")
        if i_is_key and j_is_val:
            doc.add_relation("value", doc.entities[i].id, doc.entities[j].id)
    # doc.update_doc()


def recover_all(doc: Document) -> None:
    """Recover all specs."""
    recover_on(doc)
    recover_value(doc)


def process_ann(
    filename: str,
    on: bool,
    value: bool,
    write: bool,
    write_dct: bool,
    gen_txt: bool,
) -> None:
    doc = Document(filename)
    doc.sortedby_occurrence()

    if on:
        recover_on(doc)

    if value:
        recover_value(doc)

    if write:
        if write_dct:
            relate_dct(doc)
        with open(filename.replace(".ann", "-r.ann"), "w") as fout:
            doc.output_ann(fout=fout)  # overwright existing -r.ann
    else:
        doc.output_ann()

    if gen_txt:
        fptxt = filename.replace(".ann", ".txt")
        shutil.copyfile(fptxt, fptxt.replace(".txt", "-r.txt"))

    # return doc


def main(
    filename: str,
    on: bool = True,
    value: bool = True,
    write: bool = True,
    write_dct: bool = True,
    gen_txt: bool = True,
) -> None:
    a_path = Path(filename)
    if a_path.is_dir():
        print(f"  look inside {a_path}", file=sys.stderr)
        for another_path in a_path.iterdir():
            main(
                another_path,
                on=on,
                value=value,
                write=write,
                write_dct=write_dct,
                gen_txt=gen_txt,
            )
    elif a_path.is_file() and a_path.suffix == ".ann" and "-r" not in a_path.name:
        process_ann(
            str(a_path),
            on=on,
            value=value,
            write=write,
            write_dct=write_dct,
            gen_txt=gen_txt,
        )


if __name__ == "__main__":
    # main(sys.argv[1])
    fire.Fire(main)
    # activate an interactive session to debug
    # by adding `-- --interactive` at the end of exec command
