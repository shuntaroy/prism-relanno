import csv
import sys
from pathlib import Path

import fire

from entity_types import Document, Id, Relation


def seek_line(start, end, lines):
    cumlen = 0
    cursor = 0
    # NOTE: maybe the character counts used in spans do not include new lines
    for line in lines:
        cumlen += len(line)
        cursor += 1
        if cumlen > start:
            break
    return cursor


def search_recursively(a_path):
    if a_path.is_dir():
        print(f"  look inside {a_path}", file=sys.stderr)
        for another_path in a_path.iterdir():
            search_recursively(another_path)
    elif a_path.is_file() and a_path.suffix == ".ann":
        try:
            doc = Document(str(a_path))
        except Exception as e:
            print(a_path, file=sys.stderr)
            print(e, file=sys.stderr)
            # raise
            return None

        try:
            with a_path.with_suffix(".txt").open() as fin:
                lines = fin.readlines()
        except FileNotFoundError:
            return None

        for ent in doc.entities:
            attr_val = ent.attrs.get("state")
            # time_rels = set(ent.rels_to.keys()).intersection(
            #     set(Relation.time_rels)
            # )
            if attr_val is None and ent.tag == "MedicineKey":
                lineno = seek_line(*ent.span, lines)
                print(
                    a_path,
                    lineno,
                    ent.tag,
                    ent.text,
                    # f"http://0.0.0.0:8001/index.xhtml#/{d.name}/{a_path.stem}?focus=sent~{lineno}",
                    sep="\t",
                )
                # writer.writerow(
                #     dict(
                #         file=f.name,
                #         line=lineno,
                #         tag=ent.tag,
                #         text=ent.text,
                #         # state=state,
                #         # time_rels="|".join(time_rels),
                #         link=f"http://0.0.0.0:8001/index.xhtml#/{d.name}/{f.stem}?focus=sent~{lineno}",
                #     )
                # )


def main(dirpath):
    d = Path(dirpath)
    # fout = open("search_result.csv", "w")
    # writer = csv.DictWriter(fout, ["file", "line", "tag", "state", "time_rels", "link"])
    # writer.writeheader()

    search_recursively(d)
    # fout.close()


if __name__ == "__main__":
    fire.Fire(main)
