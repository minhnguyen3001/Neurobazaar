# Neurobazaar (Under development)

**Interactive Data Visualization Tool**

![Status](https://img.shields.io/badge/status-under%20development-yellow)
[![License: BSD 3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-backend-092E20?logo=django&logoColor=white)
![Vue.js](https://img.shields.io/badge/Vue.js-3-4FC08D?logo=vuedotjs&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-database-47A248?logo=mongodb&logoColor=white)

Neurobazaar is an interactive data visualization platform that combines a Django/MongoDB backend with [Kitware's trame](https://kitware.github.io/trame/) and [VTK](https://vtk.org/) for scalable, browser-based scientific visualization, plus a Vue 3 + Vuetify front end for the application UI.

> ⚠️ **Under active development.** Structure, features, and APIs are still evolving and may change without notice.

---

## Table of Contents

- [About](#about)
- [Key Capabilities](#key-capabilities)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Running the App](#running-the-app)
- [Building for Production](#building-for-production)
- [Testing](#testing)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## About

Neurobazaar pairs a Python/Django backend with the [trame](https://kitware.github.io/trame/) framework and [VTK](https://vtk.org/) to serve interactive, data-driven visualizations straight from Python — no hand-written JavaScript rendering code required. A Vue 3 + Vuetify front end (bundled with Vite) provides the surrounding application shell, while Dask and boost-histogram handle scalable processing of larger-than-memory datasets.

> _Add more project-specific context here — goals, target users, sample datasets, or a link to a live demo._

## Key Capabilities

- **Interactive 3D/2D visualization** rendered through VTK and [vtk.js](https://kitware.github.io/vtk-js/), running directly in the browser
- **Python-driven visualization apps** via trame — write visualization logic in Python and reactively drive a web UI without a separate hand-rolled frontend for the viz layer
- **Scalable data processing** with [Dask](https://www.dask.org/) for parallel and out-of-core computation on datasets too large to fit in memory
- **Fast histogramming** of large datasets using `boost-histogram` and `dask-histogram`
- **Django + MongoDB backend** for managing application data and state
- **Modern reactive front end** built with Vue 3, Vuetify 3, and Vite

## Tech Stack

### Backend
- Python, Django
- MongoDB via `pymongo`
- NumPy, Pandas, Matplotlib, scikit-learn

### Visualization
- [trame](https://kitware.github.io/trame/) — `trame-server`, `trame-client`, `trame-components`, `trame-vuetify`, `trame-vtk`, `trame-matplotlib`
- [VTK](https://vtk.org/) (Python) and [`@kitware/vtk.js`](https://kitware.github.io/vtk-js/) (browser)

### Data Processing
- [Dask](https://www.dask.org/) — `dask[complete]`, `dask-histogram`
- `boost-histogram`

### Frontend
- Vue 3 + Vuetify 3
- Vite, with `vue-vtk-js` and `wslink`
- `django-vite` to wire the Vite build into Django templates

## Project Structure

```
Neurobazaar/
├── neurobazaar/        # Django project (settings, URLs, WSGI/ASGI config)
├── home/               # Django app
├── djangotesting/      # Django app / experiments
├── trame/              # trame-based visualization application(s)
├── vtk/                # VTK source (git submodule → gitlab.kitware.com/vtk/vtk)
├── static/src/         # Vue front-end source (bundled by Vite)
├── templates/          # Django HTML templates
├── Minh/               # Author's working directory
├── .mn/                # Project configuration
├── manage.py           # Django management entry point
├── requirements.txt    # Python dependencies
├── package.json        # Frontend (Vue/Vite) dependencies & scripts
├── vite.config.js      # Vite build configuration
├── test_app.py         # Application tests
├── .gitmodules         # Git submodule definitions
└── LICENSE             # BSD 3-Clause license
```

> A few directories (`Minh/`, `.mn/`) are working/config folders that aren't fully documented yet — flesh this section out as the project settles.

## Prerequisites

- Python 3.x (a recent 3.10+ release is recommended)
- [Node.js and npm](https://nodejs.org/)
- [MongoDB](https://www.mongodb.com/try/download/community), running locally or accessible remotely
- [Git](https://git-scm.com/), with submodule support

## Getting Started

### 1. Clone the repository

This repo declares a git submodule for VTK, so clone with `--recurse-submodules`:

```bash
git clone --recurse-submodules https://github.com/minhnguyen3001/Neurobazaar.git
cd Neurobazaar
```

Already cloned without submodules? Pull them in with:

```bash
git submodule update --init --recursive
```

### 2. Set up the Python backend

```bash
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Set up the frontend

```bash
npm install
```

### 4. Configure MongoDB

Start (or point to) a MongoDB instance, then update the connection details used by `pymongo` in `neurobazaar/settings.py` to match your environment.

### 5. Apply Django migrations

```bash
python manage.py migrate
```

Optionally, create an admin user:

```bash
python manage.py createsuperuser
```

## Running the App

During development, run the Django backend and the Vite dev server side by side:

```bash
# Terminal 1 — Django backend
python manage.py runserver

# Terminal 2 — Vite dev server (hot-reloading frontend)
npm run dev
```

Then open `http://127.0.0.1:8000/` in your browser.

## Building for Production

```bash
npm run build
python manage.py collectstatic
```

## Testing

Run the backend test suite with Django's test runner:

```bash
python manage.py test
```

`test_app.py` can also be run directly if it's structured as a standalone script:

```bash
python test_app.py
```

## Roadmap

- [ ] Pin dependency versions in `requirements.txt` / `package.json` for reproducible installs
- [ ] Document required environment variables and MongoDB configuration
- [ ] Double check `.gitmodules` — the `trame-tutorial` entry has no `path` set, which may prevent it from checking out correctly
- [ ] Add screenshots and usage examples to this README
- [ ] Add automated tests and CI
- [ ] Stabilize app structure and public API

## Contributing

Contributions, issues, and feature requests are welcome.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m "Add your feature"`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a pull request

## License

This project is licensed under the **BSD 3-Clause License** — see [LICENSE](LICENSE) for details.

## Acknowledgments

- [Kitware](https://www.kitware.com/) for [trame](https://kitware.github.io/trame/) and [VTK](https://vtk.org/)
- [Vue.js](https://vuejs.org/), [Vuetify](https://vuetifyjs.com/), and [Vite](https://vitejs.dev/)
- [Dask](https://www.dask.org/) and the broader scientific Python ecosystem

---

Maintained by [@minhnguyen3001](https://github.com/minhnguyen3001)
