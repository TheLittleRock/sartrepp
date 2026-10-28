# Simulation of $J/\psi$ Photoproduction in $p+p$ Collisions at $\sqrt{s} = 510\text{ GeV}$ with Sartre

**Author**: **Štěpán Skalka**  
*Faculty of Nuclear Sciences and Physical Engineering, Czech Technical University in Prague*  

[![Build & Deploy Jupyter Book](https://github.com/TheLittleRock/sartrepp/actions/workflows/deploy-book.yml/badge.svg)](https://github.com/TheLittleRock/sartrepp/actions/workflows/deploy-book.yml)
[![Pages](https://img.shields.io/badge/GitHub%20Pages-Live%20Book-059669)](https://TheLittleRock.github.io/sartrepp/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

---

## Executive Summary & Physics Context

This repository hosts the simulation, analysis, and documentation pipeline for the Master Thesis project studying central exclusive $J/\psi \rightarrow e^+e^-$ photoproduction in proton-proton ($p+p$) Ultra-Peripheral Collisions (UPCs) at the Relativistic Heavy Ion Collider (RHIC) with center-of-mass energy $\sqrt{s} = 510\text{ GeV}$.

The project explores the predictions of the microscopic **Color Dipole Model** implemented in the **Sartre 2** Monte Carlo event generator (`bSat`/`IPsat` with gluon saturation and `bNonSat`/`IPnonsat` linear evolution) and compares them to:
1. **STAR Experimental Data** at $\sqrt{s} = 510\text{ GeV}$ from RHIC Run 17 (both without forward Roman Pot tagging and with tagged forward recoil protons).
2. **STARlight Monte Carlo** simulations (the classical equivalent photon baseline historically used in experimental UPC analyses).
3. Prior work documented in the 2026 CTU Diploma Thesis by **Michal Vranovský**, *"Study of photoproduction of $J/\psi$ in $p+p$ collisions at $510\text{ GeV}$"*.

---

## Quick-Start (TL;DR)

If you have a fresh Linux machine (Ubuntu 22.04 / 24.04 / 26.04 LTS), execute these commands to set up the entire environment and run the simulation:

```bash
# 1. Install system build tools and scientific libraries
sudo apt update && sudo apt install -y \
    build-essential cmake git wget curl python3 python3-venv python3-pip \
    libgsl-dev libtbb-dev zlib1g-dev libpng-dev libjpeg-dev libunuran-dev

# 2. Clone the repository
git clone https://github.com/TheLittleRock/sartrepp.git
cd sartrepp

# 3. Download and unpack CERN ROOT (Choose matching version from https://root.cern/install/all_releases/)
mkdir -p root_install
wget https://root.cern/download/root_v6.40.04.Linux-ubuntu26.04-x86_64-gcc15.2.tar.gz
tar -xzf root_v6.40.04.Linux-ubuntu26.04-x86_64-gcc15.2.tar.gz -C root_install --strip-components=1
rm root_v6.40.04.Linux-ubuntu26.04-x86_64-gcc15.2.tar.gz

# 4. Download and compile Pythia 8.318
source root_install/bin/thisroot.sh
wget https://pythia.org/releases/pythia83/pythia8318.tgz
tar -xzf pythia8318.tgz && cd pythia8318
./configure --prefix=$(pwd)/../pythia8_install --with-root=$ROOTSYS --cxx-common="-O3 -fPIC -std=c++23"
make -j$(nproc) && make install && cd .. && rm -rf pythia8318 pythia8318.tgz

# 5. Patch and compile Sartre 2
cd sartre_src
patch -p1 < ../sartre2_modern_gcc_patches.patch
mkdir -p build && cd build
cmake .. \
    -DCMAKE_INSTALL_PREFIX=$(pwd)/../../sartre_install \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_STANDARD=23 \
    -DPYTHIA8_DIR=$(pwd)/../../pythia8_install
make -j$(nproc) && make install && cd ../..

# 6. Setup Python virtual environment with automatic environment hooks
python3 -m venv .venv
# (Append environment hooks block from Section 2.5 to .venv/bin/activate)
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 7. Download Sartre UPC tables
python3 sartre_install/sartre/bin/getSartreTables.py --sys=ep --sat=bSat --part=jpsi --set=HMPZ --upc
python3 sartre_install/sartre/bin/getSartreTables.py --sys=ep --sat=bNonSat --part=jpsi --set=HMPZ --upc

# 8. Compile the simulation driver binary
g++ -O3 -std=c++23 simulation/sartre_pp_jpsi.cxx \
    -I$SARTRE_DIR/include \
    -I$ROOTSYS/include \
    -I$PYTHIA8/include \
    -L$SARTRE_DIR/lib -lsartre -lgemini -lcuba \
    -L$PYTHIA8/lib -lpythia8 \
    -L$ROOTSYS/lib $(root-config --cflags --libs) -lEG -lMathMore -lUnuran \
    -lgsl -lgslcblas \
    -o simulation/sartre_pp_jpsi

# 9. Run the simulation
# Minimalist test run (1,000 events):
python3 scripts/run_sartre_single.py --events 1000 --seed 20261025

# Multi-core production run (100,000 events per model across CPU workers):
python3 scripts/run_parallel_sartre.py --events 100000 --model all --workers 12

# 10. Build the interactive Jupyter Book
jupyter-book build book/
```

---

## 1. System Requirements & Host Prerequisites

The pipeline is tested on 64-bit Linux distributions (Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, Ubuntu 26.04 LTS, Debian 12, or RHEL/CentOS 9).

### 1.1 Verifying Your Host System
```bash
lsb_release -a
uname -m
gcc --version
```
*Requirements*: x86_64 CPU architecture, GCC $\ge 11$ (GCC 13/14/15 supported with C++23), at least 8 GB RAM, and $\ge 25\text{ GB}$ free disk space.

### 1.2 Installing System Build Packages
```bash
sudo apt update
sudo apt install -y \
    build-essential \
    cmake \
    git \
    wget \
    curl \
    python3 \
    python3-venv \
    python3-pip \
    libgsl-dev \
    libtbb-dev \
    zlib1g-dev \
    libpng-dev \
    libjpeg-dev \
    libgif-dev \
    libtiff-dev \
    libfftw3-dev \
    libcfitsio-dev \
    libxpm-dev \
    libxft-dev \
    libunuran-dev
```

---

## 2. Step-by-Step Environment Setup & Compilation

Follow this sequence to ensure all libraries link cleanly without ABI conflicts.

### 2.1 CERN ROOT Installation (`root_install/`)

1. **Download Official Precompiled Binary**:
   Match the binary to your Linux distribution:
   * **Ubuntu 26.04 LTS**:
     ```bash
     mkdir -p root_install
     wget https://root.cern/download/root_v6.40.04.Linux-ubuntu26.04-x86_64-gcc15.2.tar.gz
     tar -xzf root_v6.40.04.Linux-ubuntu26.04-x86_64-gcc15.2.tar.gz -C root_install --strip-components=1
     rm root_v6.40.04.Linux-ubuntu26.04-x86_64-gcc15.2.tar.gz
     ```
   *(For other distributions or versions, see [https://root.cern/install/all_releases/](https://root.cern/install/all_releases/)).*

2. **Verify ROOT**:
   ```bash
   source root_install/bin/thisroot.sh
   root-config --version
   ```

---

### 2.2 Pythia 8.318 Installation (`pythia8_install/`)

Pythia 8 is utilized by Sartre for vector meson decay kinematics and inclusive diffractive fragmentation.

1. **Download, Configure, and Build with ROOT Support**:
   Ensure `thisroot.sh` is sourced so that `$ROOTSYS` is defined:
   ```bash
   source root_install/bin/thisroot.sh

   wget https://pythia.org/releases/pythia83/pythia8318.tgz
   tar -xzf pythia8318.tgz
   cd pythia8318

   ./configure \
       --prefix=$(pwd)/../pythia8_install \
       --with-root=$ROOTSYS \
       --cxx-common="-O3 -fPIC -std=c++23"

   make -j$(nproc)
   make install
   cd ..
   rm -rf pythia8318 pythia8318.tgz
   ```

2. **Verify Pythia 8**:
   ```bash
   ./pythia8_install/bin/pythia8-config --version
   # Expected output: 8.318
   ```

---

### 2.3 Sartre 2 Compilation & Upstream Patch Guide (`sartre_install/`)

Sartre 2 is the official diffractive vector meson photoproduction event generator developed by Tobias Toll and Thomas Ullrich.

When cloning Sartre (version 2.20) from upstream (`https://github.com/tobiastoll/sartre`), you must apply build patches for modern GCC (GCC 13/14/15) and C++23.

#### Applying the Patch:
```bash
cd sartre_src
patch -p1 < ../sartre2_modern_gcc_patches.patch
cd ..
```

#### Compiling and Installing Sartre:
```bash
source root_install/bin/thisroot.sh

mkdir -p sartre_src/build
cd sartre_src/build

cmake .. \
    -DCMAKE_INSTALL_PREFIX=$(pwd)/../../sartre_install \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_STANDARD=23 \
    -DPYTHIA8_DIR=$(pwd)/../../pythia8_install

make -j$(nproc)
make install
cd ../..
```

> [!NOTE]
> `CMAKE_INSTALL_PREFIX` is set to `$(pwd)/../../sartre_install`. Because Sartre's internal CMake scripts install into `${CMAKE_INSTALL_PREFIX}/sartre/`, the final directory becomes `sartre_install/sartre/`, exactly matching `$SARTRE_DIR`.

#### Technical Inventory of Applied Patches & Necessity Audit:
| # | File | Issue & Root Cause | Exact Modification | Needed? |
| :--- | :--- | :--- | :--- | :---: |
| **1** | `cuba/src/common/stddecl.h` | **C23 bool keyword**: GCC 15 defaults to C23 where `bool`, `true`, `false` are standard keywords. Cuba 4.2.2's `typedef enum { false, true } bool;` triggers a compiler error. | Wrapped declaration in `#if defined(__STDC_VERSION__) && __STDC_VERSION__ >= 202311L #include <stdbool.h> #else ... #endif`. | **YES** |
| **2** | `cuba/makefile.in` | **Parallel archive race condition**: Concurrent `make -j` runs multiple `ar` commands on `libcuba.a`, corrupting the archive. | Added `.NOTPARALLEL:` to top of `makefile.in`. | **YES** |
| **3** | `cmake/modules/FindPythia8.cmake` | **CMake syntax error**: Upstream has `elseif()` with no argument on line 34. | Replaced `elseif()` with `else()`. | **YES** |
| **4** | `src/Settings.cpp` | **Missing math header**: Under modern GCC C++23, standard library headers have removed transitive includes of `<cmath>`, causing `sqrt` to be undeclared. | Added explicit `#include <cmath>`. | **YES** |
| **5** | `src/TableGeneratorSettings.cpp` | **Missing algorithm header**: Under GCC 15 / C++23, `std::sort` requires explicit inclusion of `<algorithm>`. Without it, compilation fails with `error: 'sort' is not a member of 'std'`. | Added explicit `#include <algorithm>`. | **YES** |
| **6** | `CMakeLists.txt` | **C++23 standard consistency**: Ensures Sartre uses C++23 matching CERN ROOT 6.40 ABI. Upstream line 50 set `CMAKE_CXX_STANDARD 17`, overriding user flags and causing ROOT header warnings. | Changed `set(CMAKE_CXX_STANDARD 17)` $\rightarrow$ `23` at line 50. | **YES** |

> [!TIP]
> **Are all fixes in the original patch needed?**
> The old patch attempted to inject `CFLAGS=-std=gnu17` into `src/CMakeLists.txt` for Cuba. That hunk failed because upstream context lines had changed (`BUILD_COMMAND make lib`). That change was also **redundant**: patching `cuba/src/common/stddecl.h` (Fix 1) allows Cuba to compile cleanly under C23 directly, eliminating the need to alter `src/CMakeLists.txt`.

---

### 2.4 Downloading Sartre UPC Tables

Sartre evaluates diffractive amplitudes by interpolating precomputed color dipole cross-section tables. For proton-proton UPCs ($A=1$), download the dipole tables using Sartre's built-in downloader:

```bash
export SARTRE_DIR=$(pwd)/sartre_install/sartre

# Download bSat (IPsat gluon saturation) tables for J/psi (particle 443)
python3 sartre_install/sartre/bin/getSartreTables.py --sys=ep --sat=bSat --part=jpsi --set=HMPZ --upc

# Download bNonSat (linear DGLAP evolution) tables for J/psi (particle 443)
python3 sartre_install/sartre/bin/getSartreTables.py --sys=ep --sat=bNonSat --part=jpsi --set=HMPZ --upc
```

*Verification*: Check that the ROOT table files are present:
```bash
ls -lh sartre_install/sartre/tables/1/bSat/443/
ls -lh sartre_install/sartre/tables/1/bNonSat/443/
```
You should see `UPC-A1-bSat-jpsi-HMPZ-mean_A-T.root`, `UPC-A1-bSat-jpsi-HMPZ-mean_A2-T.root`, etc.

---

### 2.5 Python Virtual Environment (`.venv`) with Automatic Environment Hooks

To avoid manually setting environment variables every time a new terminal is opened, the virtual environment activation script (`.venv/bin/activate`) includes automatic environment hooks.

1. **Create the Virtual Environment**:
   ```bash
   python3 -m venv .venv
   ```

2. **Inject Automatic Environment Hooks**:
   Append the following block to `.venv/bin/activate`:
   ```bash
   cat << 'EOF' >> .venv/bin/activate

   # ==============================================================================
   # Automatic Environment Hooks for CERN ROOT, Pythia 8, and Sartre
   # ==============================================================================
   _PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

   # Source CERN ROOT
   if [ -f "$_PROJ_ROOT/root_install/bin/thisroot.sh" ]; then
       source "$_PROJ_ROOT/root_install/bin/thisroot.sh"
   fi

   # Pythia 8 Configuration
   export PYTHIA8="$_PROJ_ROOT/pythia8_install"
   export PYTHIA8DATA="$PYTHIA8/share/Pythia8/xmldoc"
   export PATH="$PYTHIA8/bin:$PATH"
   export LD_LIBRARY_PATH="$PYTHIA8/lib:$LD_LIBRARY_PATH"

   # Sartre 2 Configuration
   export SARTRE_DIR="$_PROJ_ROOT/sartre_install/sartre"
   export PATH="$SARTRE_DIR/bin:$PATH"
   export LD_LIBRARY_PATH="$SARTRE_DIR/lib:$LD_LIBRARY_PATH"
   # ==============================================================================
   EOF
   ```

3. **Install Dependencies**:
   ```bash
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Verify Environment**:
   ```bash
   python3 -c "import ROOT, uproot, awkward, vector; print('ROOT Version:', ROOT.gROOT.GetVersion()); print('Uproot Version:', uproot.__version__)"
   ```

---

## 3. Compiling the Simulation Driver (`simulation/sartre_pp_jpsi`)

The simulation driver `simulation/sartre_pp_jpsi.cxx` is the standalone C++ binary that executes the Sartre 2 simulation. It:
1. Loads the runcard settings (`runcard_bSat_HMPZ.txt` or `runcard_bNonSat_HMPZ.txt`).
2. Implements symmetric random beam reversal (`RotateX(M_PI)`) so both protons have equal $50\%$ probability of acting as the photon emitter.
3. Decays the vector meson into $e^+e^-$ pairs using Sartre's `TwoBodyVectorMesonDecay` engine (preserving $s$-channel helicity conservation).
4. Populates a flat ROOT `TTree` with full event kinematics (`jpsi_pt`, `jpsi_y`, `em_pt`, `em_eta`, `ep_pt`, `ep_eta`, `p_pom_px`, `p_pom_py`, `p_gamma_px`, `p_gamma_py`, `t`, `xpom`, `W`).
5. Stores the total integrated cross section $\sigma$ (in nb) and event count in a summary `TH1D` histogram (`histoForCSandNumberOfEvents`).

### 3.1 Compilation Command
```bash
source .venv/bin/activate

g++ -O3 -std=c++23 simulation/sartre_pp_jpsi.cxx \
    -I$SARTRE_DIR/include \
    -I$ROOTSYS/include \
    -I$PYTHIA8/include \
    -L$SARTRE_DIR/lib -lsartre -lgemini -lcuba \
    -L$PYTHIA8/lib -lpythia8 \
    -L$ROOTSYS/lib $(root-config --cflags --libs) -lEG -lMathMore -lUnuran \
    -lgsl -lgslcblas \
    -o simulation/sartre_pp_jpsi
```

### 3.2 Compilation Flags Explained
| Flag / Parameter | Purpose & Technical Rationale |
| :--- | :--- |
| `g++` | GNU C++ compiler. |
| `-O3` | **Maximum compiler optimization level**. Enables vectorization and function inlining for event throughput (~10–15 events/s per core). |
| `-std=c++23` | Sets ISO C++ 2023 dialect, matching CERN ROOT 6.40 ABI. |
| `-I$SARTRE_DIR/include` | Header search path for Sartre 2 class definitions (`Sartre.h`, `Event.h`, `Settings.h`). |
| `-I$ROOTSYS/include` | Header search path for CERN ROOT classes (`TLorentzVector.h`, `TTree.h`, `TFile.h`, `TRandom3.h`). |
| `-I$PYTHIA8/include` | Header search path for Pythia 8. |
| `-L$SARTRE_DIR/lib -lsartre -lgemini -lcuba` | Links the Sartre 2 core library, Gemini nuclear breakup engine, and Cuba integration library. |
| `-L$PYTHIA8/lib -lpythia8` | Links the Pythia 8 physics library. |
| `$(root-config --cflags --libs)` | Expands required ROOT compiler and core linker flags. |
| `-lEG -lMathMore -lUnuran` | Links ROOT's Event Generator database (`TDatabasePDG`), mathematical special functions (`ROOT::Math::cyl_bessel_k`), and UnuRan random generator interface (`TUnuran`). |
| `-lgsl -lgslcblas` | Links the GNU Scientific Library for numerical integration. |

---

## 4. Running Sartre Simulations

### 4.1 Example Runcard for $p+p$ Photoproduction (`simulation/runcard_bSat_HMPZ.txt`)

Below is the complete, line-by-line annotated example runcard for central exclusive $J/\psi \rightarrow e^+e^-$ photoproduction in $p+p$ collisions at $\sqrt{s} = 510\text{ GeV}$:

```ini
#==============================================================================
# Sartre UPC Runcard: bSat (IPsat) with HMPZ Parameter Set
# System: p + p -> p + J/psi + p @ sqrt(s) = 510 GeV
# Decay:  J/psi -> e+ e- (userInt = 11)
#==============================================================================

# --- Beam & Collision System Kinematics ---
eBeamEnergy = 255.0       # Energy of Beam 1 (GeV). In UPC, this is the proton acting as photon source.
hBeamEnergy = 255.0       # Energy of Beam 2 (GeV), the hadron target proton (sqrt(s) = 2 * 255 = 510 GeV).
A = 1                     # Mass number of hadron target (A = 1 for proton).
UPCA = 1                  # Mass number of projectile emitting the quasi-real photon (UPCA = 1 for proton).
UPC = true                # Enables Ultra-Peripheral Collision mode (Weizsaecker-Williams photon flux).

# --- Event Generation Volume & Verbosity ---
numberOfEvents = 100000   # Default number of events to simulate (can be overridden via command line).
timesToShow = 10          # Progress update frequency during table initialization.
verbose = false           # Suppresses verbose generator debug logs.
verboseLevel = 0          # Verbosity level (0 = quiet, 1 = informative, 2 = debug).

# --- Output Storage ---
rootfile = data/sartre_bSat_100k.root   # Default target ROOT output file.

# --- Microscopic Physics Model ---
dipoleModel = bSat                  # Color dipole model: 'bSat' (IPsat gluon saturation) or 'bNonSat' (linear DGLAP).
dipoleModelParameterSet = HMPZ      # Parameter fit: 'HMPZ' (Kowalski, Motyka, Watt 2006) or 'STU'.
vectorMesonId = 443                 # PDG Monte Carlo particle code (443 = J/psi vector meson).
tableSetType = total_and_coherent   # Dipole amplitude table lookup mode.

# --- Vector Meson Decay Channel ---
userInt = 11              # User flag passed to decay engine: 11 = electron (decays J/psi -> e+ e-).

# --- Quantum Mechanical & Amplitude Corrections ---
correctForRealAmplitude = true      # Incorporates real-to-imaginary amplitude ratio via dispersion relations.
correctSkewedness = true            # Applies off-forward gluon skewedness factor Rg for unequal x and x'.
maxLambdaUsedInCorrections = 0.1    # Upper bound on gluon anomalous dimension exponent lambda.

# --- Nuclear & Electromagnetic Engines ---
enableNuclearBreakup = false        # Gemini breakup engine (false for proton targets A = 1).
applyPhotonFlux = true              # Applies the Weizsaecker-Williams photon flux of the relativistic proton.
seed = 20261025                     # Base pseudo-random generator seed (TRandom3).
```

---

### 4.2 Running with the Minimalist Python Script (`scripts/run_sartre_single.py`)

For test runs, parameter verification, or single-core generation, use `scripts/run_sartre_single.py`:

```bash
source .venv/bin/activate

# Quick test generating 1,000 events with bSat:
python3 scripts/run_sartre_single.py \
    --runcard simulation/runcard_bSat_HMPZ.txt \
    --output data/test_bSat_1k.root \
    --events 1000 \
    --seed 20261025

# Generate 1,000 events with bNonSat:
python3 scripts/run_sartre_single.py \
    --runcard simulation/runcard_bNonSat_HMPZ.txt \
    --output data/test_bNonSat_1k.root \
    --events 1000 \
    --seed 20261026
```

#### Key Arguments:
- `--runcard`: Path to the runcard text file (default: `simulation/runcard_bSat_HMPZ.txt`).
- `--output`: Path to write the output ROOT file (default: `data/test_single_output.root`).
- `--events`: Number of events to generate (default: `1000`).
- `--seed`: Integer random seed for the pseudo-random generator (default: `20261025`).
- `--cs`: Optional precomputed cross section in nanobarns (skips runtime table integration if known).

---

### 4.3 Running with the Multi-Core Parallel Script (`scripts/run_parallel_sartre.py`)

Generating $100{,}000$ high-precision events on a single CPU core takes $\sim 3\text{ hours}$ per model. The multi-core orchestrator `scripts/run_parallel_sartre.py` distributes event generation across multiple CPU worker processes concurrently:

```bash
source .venv/bin/activate

# Simulate 100,000 events for both bSat and bNonSat models across 12 CPU cores:
python3 scripts/run_parallel_sartre.py --events 100000 --model all --workers 12

# Simulate only the bSat model with 8 cores:
python3 scripts/run_parallel_sartre.py --events 100000 --model bSat --workers 8
```

#### How the Multi-Core Engine Works:
1. **Even Event Partitioning**: Splits the requested 100,000 events into $N$ equal chunks (e.g. $8{,}334$ events per worker for 12 workers).
2. **Statistically Independent Seeds**: Each worker $k \in \{1, \dots, N\}$ receives an independent random seed:
   $$\text{Seed}_k = \text{BaseSeed} + 100 \times k$$
   Because ROOT's `TRandom3` has a period of $2^{19937}-1$, disjoint seeds guarantee zero statistical correlation.
3. **Low-Priority Execution**: Workers run under `nice -n 10` priority, ensuring the system remains responsive.
4. **Automated Merging**: When all chunks finish, the script automatically merges the ROOT trees and cross-section histograms using CERN ROOT's `hadd` utility into the final consolidated dataset:
   * `data/sartre_bSat_HMPZ_100k.root` ($\sigma_{\text{tot}} = 35.1315\text{ nb}$)
   * `data/sartre_bNonSat_HMPZ_100k.root` ($\sigma_{\text{tot}} = 39.2815\text{ nb}$)
5. **Cross-Section Metadata**: Appends execution benchmarks and cross sections to `data/cross_sections.json`.

---

## 5. Interactive Jupyter Book & GitHub Actions CI/CD

The repository includes an interactive companion book documenting the simulation benchmarks and official Sartre 2 documentation.

### 5.1 Building the Jupyter Book Locally
```bash
source .venv/bin/activate
jupyter-book build book/
```
The compiled HTML pages are located at `book/_build/html/index.html`. You can open and preview them in your browser:
```bash
xdg-open book/_build/html/index.html
# Or paste into your browser: file:///path/to/sartrepp/book/_build/html/index.html
```

### 5.2 Automated GitHub Actions Deployment
On every push to the `main` branch, the workflow `.github/workflows/deploy-book.yml` automatically compiles and deploys the Jupyter Book to GitHub Pages:
- **Workflow configuration**: `.github/workflows/deploy-book.yml`
- **Live online book**: [https://TheLittleRock.github.io/sartrepp/](https://TheLittleRock.github.io/sartrepp/)

---

## 6. Repository Layout & Asset Inventory

```
sartrepp/
├── .github/
│   └── workflows/
│       └── deploy-book.yml         # Automated GitHub Actions: builds & deploys Jupyter Book to Pages
├── .gitignore                      # Git exclusion rules for large datasets, binaries, and virtualenvs
├── requirements.txt                # Python package dependencies (Jupyter Book, Uproot, Awkward, etc.)
├── README.md                       # Comprehensive repository documentation and guide
├── sartre2_modern_gcc_patches.patch # Clean, unified build patch for upstream Sartre 2 (GCC 15/C++23)
│
├── book/                           # 2-part interactive Jupyter Book
│   ├── _config.yml                 # Jupyter Book configuration & theme settings
│   ├── _toc.yml                    # Table of Contents
│   ├── index.md                    # Book landing page & overview
│   ├── 06_sartre_simulation_and_analysis_benchmarks.ipynb # Part 1: Benchmark simulation notebook
│   ├── _static/                    # Custom CSS, logo emblems, and mobile navigation
│   ├── assets/                     # Vector diagrams (light and dark variants)
│   └── sartre_docs/                # Part 2: Official Sartre 2 Documentation suite
│       ├── 01_sartre_html_portal.md
│       ├── 02_sartre_overview.md
│       ├── 03_sartre_users_guide.md
│       ├── 04_sartre_upc_guide.md
│       ├── 05_sartre_runcard_ref.md
│       ├── 06_sartre_event_record.md
│       └── 07_code_modifications_summary.md
│
├── simulation/                     # C++ simulation driver & runcards
│   ├── sartre_pp_jpsi.cxx          # C++ simulation driver (symmetrization, decay, and TTree export)
│   ├── runcard_bSat_HMPZ.txt       # Runcard for bSat (IPsat gluon saturation) with HMPZ fit
│   ├── runcard_bNonSat_HMPZ.txt    # Runcard for bNonSat (linear DGLAP evolution) with HMPZ fit
│   ├── runcard_bSat_STU.txt        # Runcard for bSat with STU fit
│   └── runcard_bNonSat_STU.txt     # Runcard for bNonSat with STU fit
│
├── scripts/                        # Simulation runners & utilities
│   ├── run_sartre_single.py        # Minimalist single-instance Python simulation runner
│   ├── run_parallel_sartre.py      # Multi-core parallel simulation orchestrator
│   └── verify_simulations.py       # 5-point physical sanity verification suite
│
├── root_install/                   # CERN ROOT precompiled installation directory
├── pythia8_install/                # Pythia 8.318 compiled prefix directory
├── sartre_src/                     # Clean upstream Sartre 2 source tree (ready to patch & install)
└── data/                           # Directory for generated ROOT files and cross_sections.json
```
