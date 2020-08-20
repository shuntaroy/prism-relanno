from pathlib import Path
import csv
import fire
from entity_types import Id, Document, Relation


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


def main(dirpath):
    d = Path(dirpath)
    fout = open("search_result.csv", "w")
    writer = csv.DictWriter(fout, ["file", "line", "tag", "state", "time_rels", "link"])
    writer.writeheader()

    for f in d.iterdir():
        if f.is_file() and f.suffix == ".ann":
            print(f)
            doc = Document(str(f))
            try:
                with f.with_suffix(".txt").open() as fin:
                    lines = fin.readlines()
            except FileNotFoundError:
                continue

            for ent in doc.entities:
                state = ent.attrs.get("state")
                time_rels = set(ent.rels_to.keys()).intersection(
                    set(Relation.time_rels)
                )
                if state and time_rels:
                    lineno = seek_line(*ent.span, lines)
                    writer.writerow(
                        dict(
                            file=f.name,
                            line=lineno,
                            tag=ent.tag,
                            state=state,
                            time_rels="|".join(time_rels),
                            link=f"http://0.0.0.0:8001/index.xhtml#/{d.name}/{f.stem}?focus=sent~{lineno}",
                        )
                    )
    fout.close()


if __name__ == "__main__":
    fire.Fire(main)
