"""Generate the multi-page seed PDF (history-of-computing.pdf).

The PDF is committed to the repo so the demo seed (``eval/seed_demo.py``) does
not depend on this script at runtime. Regenerate it with:

    python seed-data/generate_pdf.py

Requires ``fpdf2`` (``pip install fpdf2``). The content is original, factual
prose written for this project, so there are no licensing constraints. Each
page covers a distinct era so retrieval across pages is easy to demonstrate.
"""

from pathlib import Path

from fpdf import FPDF

OUTPUT = Path(__file__).parent / "history-of-computing.pdf"

# (heading, body) for each page, in order.
PAGES = [
    (
        "A Brief History of Computing",
        "This short document traces the history of computing across several "
        "eras, from mechanical calculators to the global Internet. Each page "
        "covers a distinct period.\n\n"
        "Early Mechanical Calculators\n\n"
        "In the seventeenth century Blaise Pascal built a mechanical adding "
        "machine, and Gottfried Leibniz later designed a device that could "
        "also multiply. In the nineteenth century Charles Babbage designed the "
        "Analytical Engine, a general-purpose mechanical computer that was "
        "never fully built in his lifetime. Ada Lovelace, working from "
        "Babbage's designs, wrote what is often considered the first algorithm "
        "intended to be carried out by a machine, and is remembered as the "
        "first computer programmer.",
    ),
    (
        "The Theoretical Foundations",
        "In 1936 Alan Turing introduced an abstract model of computation now "
        "called the Turing machine, which formalized the idea of an algorithm "
        "and defined the limits of what can be computed. Around the same time "
        "Alonzo Church developed the lambda calculus, an equivalent model.\n\n"
        "In 1937 Claude Shannon showed that Boolean algebra could describe the "
        "behavior of electrical switching circuits, linking logic to hardware. "
        "A decade later Shannon founded information theory, giving a precise, "
        "mathematical meaning to the quantity of information measured in bits. "
        "Together these ideas form the theoretical bedrock of computer "
        "science.",
    ),
    (
        "The First Electronic Computers",
        "During the 1940s the first large-scale electronic computers were "
        "built. ENIAC, completed in 1945, used thousands of vacuum tubes and "
        "could be reprogrammed only by rewiring it physically.\n\n"
        "The decisive idea of this era was the stored-program concept, in which "
        "a computer's instructions are held in the same memory as its data. "
        "This design is commonly called the von Neumann architecture, after a "
        "1945 report by John von Neumann, and almost every general-purpose "
        "computer since has followed it.",
    ),
    (
        "The Transistor and the Integrated Circuit",
        "In 1947 researchers at Bell Labs invented the transistor, a compact, "
        "reliable replacement for the fragile vacuum tube. In 1958 the "
        "integrated circuit packed many transistors onto a single chip.\n\n"
        "In 1965 Gordon Moore observed that the number of transistors on a chip "
        "was doubling roughly every two years, an empirical trend later known "
        "as Moore's law. In 1971 Intel released the 4004, the first commercial "
        "microprocessor, placing a complete processing unit on one chip and "
        "opening the way to personal computers.",
    ),
    (
        "Networking and the Internet",
        "In 1969 ARPANET connected its first few university computers, "
        "demonstrating packet switching over long distances. In the 1970s "
        "Vinton Cerf and Robert Kahn designed the TCP/IP protocol suite, which "
        "let independent networks interconnect and became the technical "
        "foundation of the Internet.\n\n"
        "In 1989 Tim Berners-Lee proposed the World Wide Web at CERN, and by "
        "1991 the first web pages were online. The Web combined hypertext, the "
        "HTTP protocol, and the URL addressing scheme to make the Internet "
        "broadly accessible, setting the stage for the connected world of "
        "today.",
    ),
]


def generate_pdf() -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    for heading, body in PAGES:
        pdf.add_page()
        pdf.set_font("Helvetica", style="B", size=16)
        pdf.multi_cell(0, 10, heading)
        pdf.ln(4)
        pdf.set_font("Helvetica", size=12)
        pdf.multi_cell(0, 7, body)
    pdf.output(str(OUTPUT))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    generate_pdf()
