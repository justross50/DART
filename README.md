# DART – Decision Advantage in Real Time

This repository contains a self‑hosted prototype of **DART** (Decision Advantage in Real Time).  The project originated as a hackathon entry and was later updated to run without external services.  It allows users to create decision events, invite participants, capture observations/discussions/recommendations (ODRs) and explore those comments through a simple chat interface.

## Quick start guide

The application is built on Django and runs on Python 3.  It has been pared back so that it works without internet access or heavy machine‑learning dependencies.  You can run it locally on Linux, macOS or Windows.

### Prerequisites

- Python 3.10+ (tested with Python 3.11)
- `pip` package manager

### Installation

1. **Unpack the project**

   After downloading the zip archive extract it and change into the Django project directory:

   ```sh
   unzip dart_v1_gp1p6l.zip
   cd dart_v1_gp1p6l/pryoninc-amc-dart-b02487efc8b2
   ```

2. **Create a virtual environment** (recommended)

   ```sh
   python -m venv venv
   # Activate the virtual environment
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies**

   The `requirements.txt` lists Django, requests and the optional Ollama client.  Install them with:

   ```sh
   pip install -r requirements.txt
   ```

   If you do not intend to use Ollama for summarisation or chat responses you may omit the `ollama` package from the installation.  When installed, Ollama will be used to generate summaries and answer queries if models are available.

4. **Apply database migrations**

   Initialise the SQLite database with Django’s migrations:

   ```sh
   python manage.py migrate
   ```

5. **Create an admin (superuser) account**

   To log in to the application you need at least one user.  Use Django’s built‑in management command to create a superuser:

   ```sh
   python manage.py createsuperuser
   ```

   You will be prompted for a username, email address and password.  Once created, this account can be used to log in to the web interface and to invite other users.

6. **Run the development server**

   Start the server locally:

   ```sh
   python manage.py runserver
   ```

   By default Django binds to `http://127.0.0.1:8000/`.  If you are running inside a container or want to make the site visible on your network you can bind to all interfaces with:

   ```sh
   python manage.py runserver 0.0.0.0:8000
   ```

7. **Access the application**

   Open your browser and navigate to the server address.  You will be redirected to the login page.  Use the superuser credentials you created above.

   Once logged in you can:

   - **Start a new event** via the “Start Event” menu.  Enter a title and a start/end date.  The creator is automatically added as an invitee.
   - **Add comments** to an event.  Each comment consists of an observation, optional discussion and recommendation.
   - **Invite additional users** by editing the event in the Django admin (`/admin/`), or by adding them to the invitee list when creating comments.
   - **Use the chat interface** to ask questions about the collected comments.  The search uses simple string matching and a naïve sentiment classifier.  You can filter results by sentiment or adjust the number of returned results.  When summarisation is enabled, the system attempts to summarise the context; if no language model is available it falls back to extracting the first few sentences.

   - **Upload a structured CSV of comments** from the event page.  The file must contain a header row with `observation`, `discussion` and `recommendation` columns.  Each subsequent row is imported as a new comment.  This is useful for bulk‑loading data from other systems.  After import the comments appear in the chat and summary interfaces.

### Language model integration

If the [Ollama](https://ollama.com/) server is installed and running locally, the application will attempt to use it for summarisation and chat responses.  Models available to Ollama are automatically listed in the UI.  When no model has been chosen previously the system will prefer one named `gemma3n` (for example `gemma3n:latest`), falling back to the first available model if `gemma3n` is not present.  You can select another model at any time in the chat settings.

### Notes on this version

- The original DART prototype depended on `chromadb` for vector storage and the Ollama API for language generation.  Those libraries are **not required** here.  All data resides in the SQLite database and the search uses a straightforward similarity metric.
- Summaries and sentiment classification are intentionally simple so that the application functions offline.  You are welcome to integrate your own embedding model or sentiment analyser by extending the methods in `base/models.py`.
- The secret key for Django is generated dynamically on each run in `dart/settings.py`.  For production use you should set a fixed secret key and configure `ALLOWED_HOSTS` appropriately.
  In development we set `DEBUG = True` in `dart/settings.py` and allow
  connections from `localhost` and `127.0.0.1`.  If you disable debug mode
  (`DEBUG = False`) you **must** populate `ALLOWED_HOSTS` with the host names
  that will serve the application.

## Disclaimer

IT IS EXPRESSLY UNDERSTOOD THAT THE SOFTWARE IS PROVIDED WITHOUT ANY WARRANTY OF ANY TYPE OR NATURE ON AN “AS IS” AND “WITH ALL FAULTS” BASIS.  PRYON DISCLAIMS ALL EQUITABLE INDEMNITIES, AS WELL AS ALL WARRANTIES, WHETHER STATUTORY, EXPRESS OR IMPLIED, INCLUDING, BUT NOT LIMITED TO, ANY STATUTORY OR IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, TITLE, QUIET ENJOYMENT, AND NON‑INFRINGEMENT.  ANY USE OF THE SOFTWARE IS SOLELY AT THE USER’S SOLE RISK.