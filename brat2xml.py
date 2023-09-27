"""Convert brat format files to XMLs."""
from pathlib import Path

import fire

import entity_types as et


def main(path: str):
    p = Path(path)
    if p.is_dir():
        for i in p.iterdir():
            print("traverse", i)
            main(str(i))
    elif p.is_file() and p.suffix == ".ann":
        doc = et.Document(p)
        xmlstr = doc.to_xml()
        with open(p.with_suffix(".xml"), "w") as fout:
            fout.write(xmlstr)


if __name__ == "__main__":
    fire.Fire(main)
