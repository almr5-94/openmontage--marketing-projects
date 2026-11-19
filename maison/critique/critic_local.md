# Local critic: Maison (vision + reasoning models)

Run by `maison/critique/critique.py` for a human working offline with Ollama or LM Studio
(`config/local_models.yaml`).

1. The **vision** model looks at each page and answers one short question per criterion
   ("Is there generous empty space on this page? Answer with a number 1-5"), which keeps a 7B
   model reliable.
2. The **reasoning** model receives those answers, the house.yaml voice rules and the page
   text, and writes one evidence line per criterion.

Local scores are recorded beside Claude's in the same `maison_critique` artifact. The gate takes
the **lower** score of the two critics for each criterion.
