# Retrieval evaluation (2026-10-12)

Embedding model `nomic-embed-text`, top-k = 6, threshold `MIN_SIMILARITY=0.73`.

- **hit@6**: 94% of 16 on-topic questions return an expected episode
- **MRR**: 0.91
- **Off-topic rejected**: 100% of 3

| Question | Type | Result | Rank | Top similarity | Top episodes |
|---|---|---|---|---|---|
| What does Melanie Perkins say about starting Canva? | on-topic | pass | 1 | 0.83 | melanie-perkins, melanie-perkins |
| What does Brian Chesky say about running Airbnb? | on-topic | pass | 1 | 0.83 | brian-chesky, brian-chesky, karri-saarinen |
| What did Stewart Butterfield learn building Slack? | on-topic | pass | 1 | 0.76 | stewart-butterfield, stewart-butterfield |
| What does Marty Cagan say about empowered product teams? | on-topic | pass | 1 | 0.8 | marty-cagan, marty-cagan |
| How does Teresa Torres describe continuous discovery? | on-topic | pass | 1 | 0.84 | teresa-torres, teresa-torres |
| What does Geoffrey Moore say about crossing the chasm? | on-topic | pass | 1 | 0.79 | geoffrey-moore, geoffrey-moore |
| What does Karri Saarinen say about building Linear with craft? | on-topic | pass | 1 | 0.79 | karri-saarinen, karri-saarinen |
| What does Dylan Field say about Figma? | on-topic | pass | 1 | 0.83 | dylan-field, dylan-field, yuhki-yamashata |
| What does Jason Fried say about running a calm company? | on-topic | pass | 1 | 0.77 | jason-fried, jason-fried |
| What does Sarah Tavel say about the hierarchy of engagement? | on-topic | pass | 1 | 0.74 | sarah-tavel |
| How do you find product-market fit? | on-topic | pass | 1 | 0.8 | karri-saarinen, todd-jackson, todd-jackson |
| How do you hire a head of growth? | on-topic | pass | 1 | 0.79 | adam-fishman, hila-qu, adam-fishman |
| How do marketplaces get liquidity? | on-topic | pass | 2 | 0.8 | dan-hockenmaier, ramesh-johari, dan-hockenmaier |
| How should a team do product discovery with customers? | on-topic | FAIL | - | 0.75 | oji-udezue, oji-udezue, laura-schaffer |
| How do you evaluate and build AI products? | on-topic | pass | 1 | 0.83 | aishwarya-naresh-reganti-kiriti-badam, aishwarya-naresh-reganti-kiriti-badam, hamelshreya |
| How do you run a job search with a support group? | on-topic | pass | 1 | 0.76 | phyl-terry, phyl-terry |
| What is the best pizza topping? | off-topic | pass | - | - | (none) |
| Who won the cricket world cup? | off-topic | pass | - | - | (none) |
| How do I fix a car engine? | off-topic | pass | - | - | (none) |

Cases live in `backend/eval/retrieval_cases.json`; failures are listed, not hidden. A miss can mean the episode is not in the indexed sample, not only a retrieval error.
