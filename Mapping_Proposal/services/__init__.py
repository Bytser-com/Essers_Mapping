"""Business logic used by the API (routers/) and the command line (main.py).

    proposals.py         read and write proposals on the shared storage (SFTP share)
    proposal_runner.py   run the AI for one proposal and keep its status up to date
    incoming_watcher.py  start the AI automatically for every complete upload
    storage.py           (to do) SFTP upload
    jobs.py              (to do) job status for API runs

The AI pipeline itself (reading XML, Gemini, validation, Excel) stays in scripts/.
"""
