from xml.dom import minidom
from pathlib import Path
import argparse


def cat2bio(category):
    # Map categories to BIO format
    global last_category
    if category == "O":
        last_category = False
        return "O"
    elif last_category == category:
        return "I-" + category
    else:
        last_category = category
        return "B-" + category


def scandown(elements, categ, output, depth=0):
    # Scan all the docs searching for text and their tags
    for el in elements:
        if el.nodeName == "#text":
            for char in el.nodeValue:
                category = cat2bio(categ)
                output.write(char + " " + category + "\n")

        scandown(
            el.childNodes,
            el.attributes["CATEG"].value
            if el.attributes and "CATEG" in el.attributes
            else "O",
            output,
            depth + 1,
        )

    if depth == 1:
        output.write("\n")


if __name__ == "__main__":
    # Parse inline arguments
    parser = argparse.ArgumentParser(description="XML to Conll converter")
    parser.add_argument("--input", type=Path, help="The XML file to convert")
    parser.add_argument("--output", type=Path, help="The output CONLL file name")
    args = parser.parse_args()

    # Read XML input file
    xmldoc = minidom.parse(args.input)
    docs = xmldoc.getElementsByTagName("DOC")
    print("Converting " + str(len(docs)) + " documents")

    output_file_name = args.input.with_suffix(".conll")
    with open(output_file_name, "a") as output:
        last_category = False
        scandown(docs, "O", output)
