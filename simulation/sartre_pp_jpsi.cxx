//==============================================================================
//  sartre_pp_jpsi.cxx
//
//  Analysis of J/psi Photoproduction in p+p Collisions at sqrt(s) = 510 GeV
//  Author: Štěpán Skalka (Faculty of Nuclear Sciences, CTU in Prague)
//
//  ============================================================================
//  PROGRAM OVERVIEW & ARCHITECTURE:
//  ============================================================================
//  This standalone C++ program serves as the core Monte Carlo simulation driver
//  for the Sartre 2 event generator. It simulates central exclusive diffractive
//  photoproduction of J/psi vector mesons in proton-proton (p+p) Ultra-Peripheral
//  Collisions (UPCs) at RHIC energies (sqrt(s) = 510 GeV):
//
//      p + p  -->  p + J/psi + p,   with  J/psi --> e+ + e-
//
//  KEY RESPONSIBILITIES OF THIS DRIVER:
//    1. Command-Line Interface & Runcard Loading:
//       Reads runtime configuration from a Sartre runcard text file, with optional
//       command-line overrides for event count, random seed, output file path,
//       and precomputed integrated cross section.
//
//    2. Laboratory Frame Symmetrization (applyRandomBeamReversal):
//       Sartre was originally authored for asymmetric electron-hadron (e+p, e+A)
//       collisions where Beam 1 always emits the photon and Beam 2 is always
//       the hadron target. In identical-species UPCs (p+p), both colliding
//       protons have an identical (50%) quantum mechanical probability to emit
//       the quasi-real photon or serve as the diffractive Pomeron target.
//       This function restores full laboratory parity symmetry by randomly
//       rotating the final-state kinematics by 180 degrees (pi radians) around
//       the transverse x-axis.
//
//    3. Polarization-Aware Vector Meson Decay:
//       Decays the vector meson (J/psi, PDG 443) into an electron-positron
//       pair (e- [PDG 11] and e+ [PDG -11]) using Sartre's native
//       TwoBodyVectorMesonDecay engine, strictly preserving s-channel helicity
//       conservation (SCHC) and transverse vs. longitudinal decay kinematics.
//
//    4. Dual-Proton Kinematic Extraction:
//       Separates the two distinct forward outgoing protons:
//         - event->particles[2]: The scattered photon emitter (transverse
//           momentum transfer k_T ~ 20-40 MeV/c, remaining inside beam pipe).
//         - event->particles[6]: The diffractive Pomeron target proton
//           (transverse recoil p_T ~ sqrt(-t) ~ 0.2-1.0 GeV/c, tagged by STAR
//           Roman Pot detectors).
//
//    5. Flat Columnar Data Serialization:
//       Fills a standard CERN ROOT TTree ("sartre_tree") with comprehensive
//       event-level and particle-level kinematics for rapid vectorized analysis
//       using Python (uproot, awkward array, vector) or ROOT macros.
//
//    6. Cross-Section Normalization Bookkeeping:
//       Creates a 2-bin summary histogram ("histoForCSandNumberOfEvents") storing
//       the total integrated cross section (in nanobarns) and the number of
//       generated events. This schema is fully compatible with CERN ROOT's `hadd`
//       utility for parallel multi-core merges.
//==============================================================================

#include <iostream>
#include <cmath>
#include <cstdlib>
#include <string>
#include <vector>
#include <utility>

// CERN ROOT Data Structures & Utilities
#include "TFile.h"          // Binary ROOT file container
#include "TTree.h"          // Columnar hierarchical dataset
#include "TH1D.h"           // 1D histogram for cross-section metadata
#include "TLorentzVector.h" // Relativistic 4-momentum class (Px, Py, Pz, E)
#include "TRandom3.h"       // Mersenne Twister pseudo-random generator

// Sartre 2 Simulation Engine Headers
#include "Sartre.h"                  // Primary Sartre generator interface
#include "Settings.h"                // Runcard parsing & generator settings
#include "Event.h"                   // Event record containing particle graph
#include "TwoBodyVectorMesonDecay.h" // Vector meson 2-body decay engine

using namespace std;

//------------------------------------------------------------------------------
// Function: applyRandomBeamReversal
// Purpose:  Restore laboratory frame symmetry for identical colliding beams (p+p).
//
// Physics Explanation:
//   In Sartre's standard coordinate convention:
//     - Beam 1 (e or p) travels in the +z direction (positive rapidity).
//     - Beam 2 (target nucleus/proton) travels in the -z direction (negative rapidity).
//   For p+p collisions at sqrt(s) = 510 GeV, both colliding beams are identical
//   protons. Either proton can emit the quasi-real photon with equal 50% probability.
//   To model this physical symmetry, we sample a uniform random number in [0, 1).
//   If u > 0.5, we perform a 180-degree (pi radian) rotation around the x-axis:
//     Px' = Px
//     Py' = -Py
//     Pz' = -Pz  ==> Rapidities flip: y' = -y
//     E'  = E
//   This operation strictly preserves the invariant mass, transverse momentum
//   magnitude, and four-momentum conservation while ensuring that the forward/backward
//   rapidity distributions of final-state particles are symmetric around y = 0.
//------------------------------------------------------------------------------
bool applyRandomBeamReversal(Event* event)
{
    TRandom3* rnd = EventGeneratorSettings::randomGenerator();
    bool do_reverse = (rnd->Uniform(1.0) > 0.5);
    if (do_reverse) {
        for (size_t i = 0; i < event->particles.size(); ++i) {
            // RotateX(M_PI) reverses py and pz while leaving px and energy unchanged
            event->particles[i].p.RotateX(M_PI);
        }
    }
    return do_reverse;
}

//------------------------------------------------------------------------------
// Function: main
// Purpose:  Entry point for simulation driver binary.
// Arguments:
//   argv[1]: Path to Sartre runcard (e.g., runcard_bSat_HMPZ.txt) [REQUIRED]
//   argv[2]: Path to output ROOT file (e.g., output.root)         [OPTIONAL]
//   argv[3]: Number of events to generate override               [OPTIONAL]
//   argv[4]: Pseudo-random generator seed override               [OPTIONAL]
//   argv[5]: Precomputed total cross-section in nanobarns (nb)   [OPTIONAL]
//------------------------------------------------------------------------------
int main(int argc, char* argv[])
{
    if (argc < 2 || argc > 6) {
        cout << "Usage: " << argv[0] << " <runcard.txt> [output.root] [nEvents] [seed] [known_cs_nb]" << endl;
        cout << "  runcard.txt:  Path to Sartre runcard configuration file." << endl;
        cout << "  output.root:  Target output ROOT file (default: from runcard or sartre_out.root)." << endl;
        cout << "  nEvents:      Event count override (default: from runcard)." << endl;
        cout << "  seed:         Random seed override (default: from runcard)." << endl;
        cout << "  known_cs_nb:  Known total cross-section in nb to bypass runtime integration." << endl;
        return 1;
    }

    // Parse command-line parameters
    string runcard = argv[1];
    string rootfile = (argc >= 3) ? argv[2] : "";
    unsigned long cmdEvents = (argc >= 4) ? std::stoul(argv[3]) : 0;
    unsigned int cmdSeed = (argc >= 5) ? std::stoul(argv[4]) : 0;
    double cmdCrossSection = (argc >= 6) ? std::stod(argv[5]) : 0.0;

    cout << "==========================================================" << endl;
    cout << "  Sartre 2 UPC p+p Simulation: J/psi -> e+ e- @ 510 GeV" << endl;
    cout << "  Runcard: " << runcard << endl;
    if (cmdEvents > 0) cout << "  Command-line event override: " << cmdEvents << endl;
    if (cmdSeed > 0)   cout << "  Command-line seed override:  " << cmdSeed << endl;
    if (cmdCrossSection > 0) cout << "  Command-line cross-section:  " << cmdCrossSection << " nb" << endl;
    cout << "==========================================================" << endl;

    // Initialize Sartre generator core
    Sartre sartre;
    if (!sartre.init(runcard)) {
        cerr << "FATAL: Sartre initialization failed with runcard: " << runcard << endl;
        return 1;
    }

    // Access runtime generator settings
    EventGeneratorSettings* settings = sartre.runSettings();
    if (cmdSeed > 0) {
        settings->setSeed(cmdSeed);
        EventGeneratorSettings::randomGenerator()->SetSeed(cmdSeed);
    }
    if (rootfile.empty()) {
        rootfile = settings->rootfile();
    }
    if (rootfile.empty()) {
        rootfile = "sartre_out.root";
    }

    cout << "Target output ROOT file: " << rootfile << endl;
    unsigned long nEventsRequested = (cmdEvents > 0) ? cmdEvents : settings->numberOfEvents();
    cout << "Events requested: " << nEventsRequested << endl;

    // Create output ROOT container file
    TFile* outFile = new TFile(rootfile.c_str(), "RECREATE");
    if (!outFile || outFile->IsZombie()) {
        cerr << "FATAL: Could not create output ROOT file: " << rootfile << endl;
        return 1;
    }

    // =========================================================================
    // DECLARE TREE OUTPUT VARIABLES
    // =========================================================================

    // Overall Event Kinematics
    int    iEvent_val  = 0;  // Sequential event index
    double t_val       = 0;  // Mandelstam t: squared momentum transfer to target (GeV^2)
    double Q2_val      = 0;  // Photon virtuality Q^2 (GeV^2, ~0 for quasi-real UPC)
    double W_val       = 0;  // Photon-proton center-of-mass energy W_gp (GeV)
    double x_val       = 0;  // Standard DIS Bjorken-x
    double y_val       = 0;  // Lepton inelasticity variable y
    double s_val       = 0;  // Total center-of-mass energy squared (s = 510^2 GeV^2)
    double xpom_val    = 0;  // Fractional momentum loss of target proton (x_pomeron)
    int    pol_val     = 0;  // Photon polarization state: 0 = transverse, 1 = longitudinal
    int    dmode_val   = 0;  // Diffractive mode: 0 = coherent, 1 = incoherent
    int    is_reversed = 0;  // Parity reversal flag: 1 if rotated by pi, 0 otherwise

    // Vector Meson (J/psi) Kinematics
    double jpsi_px = 0, jpsi_py = 0, jpsi_pz = 0, jpsi_E = 0;
    double jpsi_pt = 0, jpsi_eta = 0, jpsi_phi = 0, jpsi_m = 0, jpsi_y = 0;

    // Daughter Electron (e-, PDG ID: 11)
    double em_px = 0, em_py = 0, em_pz = 0, em_E = 0;
    double em_pt = 0, em_eta = 0, em_phi = 0, em_m = 0;

    // Daughter Positron (e+, PDG ID: -11)
    double ep_px = 0, ep_py = 0, ep_pz = 0, ep_E = 0;
    double ep_pt = 0, ep_eta = 0, ep_phi = 0, ep_m = 0;

    // Reconstructed Dielectron Pair Kinematics (d1 + d2)
    double pair_m = 0, pair_pt = 0, pair_y = 0, pair_eta = 0;

    // Outgoing Proton 1: Photon Emitter (ultra-low pT, typically stays in beam pipe)
    double p_gamma_px = 0, p_gamma_py = 0, p_gamma_pz = 0, p_gamma_E = 0;
    double p_gamma_pt = 0, p_gamma_eta = 0, p_gamma_phi = 0, p_gamma_m = 0;

    // Outgoing Proton 2: Pomeron Target (diffractive recoil, enters Roman Pots)
    double p_pom_px = 0, p_pom_py = 0, p_pom_pz = 0, p_pom_E = 0;
    double p_pom_pt = 0, p_pom_eta = 0, p_pom_phi = 0, p_pom_m = 0;

    // Transverse Momentum Imbalance & Global Conservation Checks
    // Missing pT when only Pomeron target proton is tagged: |vec(pT_J/psi) + vec(pT_p_pom)|
    double pt_missing_pom = 0;
    // Missing pT when only photon emitter proton is tagged: |vec(pT_J/psi) + vec(pT_p_gamma)|
    double pt_missing_gamma = 0;
    // Global transverse balance: |vec(pT_J/psi) + vec(pT_p_pom) + vec(pT_p_gamma)| (must equal 0)
    double pt_balance = 0;

    // Instantiate CERN ROOT TTree
    TTree* tree = new TTree("sartre_tree", "Sartre Exclusive J/psi Photoproduction in p+p");

    // Event branches
    tree->Branch("iEvent",      &iEvent_val,  "iEvent/I");
    tree->Branch("t",           &t_val,       "t/D");
    tree->Branch("Q2",          &Q2_val,      "Q2/D");
    tree->Branch("W",           &W_val,       "W/D");
    tree->Branch("x",           &x_val,       "x/D");
    tree->Branch("y",           &y_val,       "y/D");
    tree->Branch("s",           &s_val,       "s/D");
    tree->Branch("xpom",        &xpom_val,    "xpom/D");
    tree->Branch("pol",         &pol_val,     "pol/I");
    tree->Branch("dmode",       &dmode_val,   "dmode/I");
    tree->Branch("is_reversed", &is_reversed, "is_reversed/I");

    // Vector Meson (J/psi) branches
    tree->Branch("jpsi_px",  &jpsi_px,  "jpsi_px/D");
    tree->Branch("jpsi_py",  &jpsi_py,  "jpsi_py/D");
    tree->Branch("jpsi_pz",  &jpsi_pz,  "jpsi_pz/D");
    tree->Branch("jpsi_E",   &jpsi_E,   "jpsi_E/D");
    tree->Branch("jpsi_pt",  &jpsi_pt,  "jpsi_pt/D");
    tree->Branch("jpsi_eta", &jpsi_eta, "jpsi_eta/D");
    tree->Branch("jpsi_phi", &jpsi_phi, "jpsi_phi/D");
    tree->Branch("jpsi_m",   &jpsi_m,   "jpsi_m/D");
    tree->Branch("jpsi_y",   &jpsi_y,   "jpsi_y/D");

    // Electron (e-) branches
    tree->Branch("em_px",  &em_px,  "em_px/D");
    tree->Branch("em_py",  &em_py,  "em_py/D");
    tree->Branch("em_pz",  &em_pz,  "em_pz/D");
    tree->Branch("em_E",   &em_E,   "em_E/D");
    tree->Branch("em_pt",  &em_pt,  "em_pt/D");
    tree->Branch("em_eta", &em_eta, "em_eta/D");
    tree->Branch("em_phi", &em_phi, "em_phi/D");
    tree->Branch("em_m",   &em_m,   "em_m/D");

    // Positron (e+) branches
    tree->Branch("ep_px",  &ep_px,  "ep_px/D");
    tree->Branch("ep_py",  &ep_py,  "ep_py/D");
    tree->Branch("ep_pz",  &ep_pz,  "ep_pz/D");
    tree->Branch("ep_E",   &ep_E,   "ep_E/D");
    tree->Branch("ep_pt",  &ep_pt,  "ep_pt/D");
    tree->Branch("ep_eta", &ep_eta, "ep_eta/D");
    tree->Branch("ep_phi", &ep_phi, "ep_phi/D");
    tree->Branch("ep_m",   &ep_m,   "ep_m/D");

    // Reconstructed dielectron pair branches
    tree->Branch("pair_m",   &pair_m,   "pair_m/D");
    tree->Branch("pair_pt",  &pair_pt,  "pair_pt/D");
    tree->Branch("pair_y",   &pair_y,   "pair_y/D");
    tree->Branch("pair_eta", &pair_eta, "pair_eta/D");

    // Photon-emitting proton branches
    tree->Branch("p_gamma_px",  &p_gamma_px,  "p_gamma_px/D");
    tree->Branch("p_gamma_py",  &p_gamma_py,  "p_gamma_py/D");
    tree->Branch("p_gamma_pz",  &p_gamma_pz,  "p_gamma_pz/D");
    tree->Branch("p_gamma_E",   &p_gamma_E,   "p_gamma_E/D");
    tree->Branch("p_gamma_pt",  &p_gamma_pt,  "p_gamma_pt/D");
    tree->Branch("p_gamma_eta", &p_gamma_eta, "p_gamma_eta/D");
    tree->Branch("p_gamma_phi", &p_gamma_phi, "p_gamma_phi/D");
    tree->Branch("p_gamma_m",   &p_gamma_m,   "p_gamma_m/D");

    // Pomeron-target proton branches
    tree->Branch("p_pom_px",  &p_pom_px,  "p_pom_px/D");
    tree->Branch("p_pom_py",  &p_pom_py,  "p_pom_py/D");
    tree->Branch("p_pom_pz",  &p_pom_pz,  "p_pom_pz/D");
    tree->Branch("p_pom_E",   &p_pom_E,   "p_pom_E/D");
    tree->Branch("p_pom_pt",  &p_pom_pt,  "p_pom_pt/D");
    tree->Branch("p_pom_eta", &p_pom_eta, "p_pom_eta/D");
    tree->Branch("p_pom_phi", &p_pom_phi, "p_pom_phi/D");
    tree->Branch("p_pom_m",   &p_pom_m,   "p_pom_m/D");

    // Transverse missing and balance branches
    tree->Branch("pt_missing_pom",   &pt_missing_pom,   "pt_missing_pom/D");
    tree->Branch("pt_missing_gamma", &pt_missing_gamma, "pt_missing_gamma/D");
    tree->Branch("pt_balance",       &pt_balance,       "pt_balance/D");

    // Vector meson decay engine initialization
    TwoBodyVectorMesonDecay decayEngine;
    const int daughterID = 11; // PDG 11 = electron; decay produces e- (11) and e+ (-11)

    cout << "Beginning event generation loop for " << nEventsRequested << " events..." << endl;
    int printInterval = nEventsRequested / 10;
    if (printInterval > 1000) printInterval = 1000;
    if (printInterval < 1) printInterval = 1;

    unsigned long nValidEvents = 0;

    // =========================================================================
    // MAIN MONTE CARLO EVENT GENERATION LOOP
    // =========================================================================
    for (unsigned long iEvt = 0; iEvt < nEventsRequested; ++iEvt) {
        // Sample one complete physical event from Sartre
        Event* event = sartre.generateEvent();
        if (!event) {
            cerr << "WARNING: Null event generated at index " << iEvt << "; skipping." << endl;
            continue;
        }

        // Apply symmetric random beam reversal for identical-species p+p collisions
        bool rev = false;
        if (settings->UPC() && settings->A() == settings->UPCA()) {
            rev = applyRandomBeamReversal(event);
        }
        is_reversed = rev ? 1 : 0;

        // Extract generated vector meson (particle index 4 in Sartre event graph)
        TLorentzVector vm = event->particles[4].p;
        if (vm.E() <= 0 || vm.M() <= 0 || !std::isfinite(vm.E()) ||
            !std::isfinite(vm.Px()) || !std::isfinite(vm.Py()) || !std::isfinite(vm.Pz())) {
            cerr << "WARNING: Skipping unphysical vector meson kinematics at event " << iEvt << endl;
            continue;
        }

        // Decay the vector meson J/psi -> e+ e- according to its polarization state
        // d1 is particle (e-), d2 is antiparticle (e+)
        pair<TLorentzVector, TLorentzVector> daughters = decayEngine.decayVectorMeson(vm, *event, daughterID);
        TLorentzVector d1 = daughters.first;  // e-
        TLorentzVector d2 = daughters.second; // e+

        // Outgoing forward protons:
        // Index 2 is the scattered photon emitter (quasi-elastic emitter, minimal pT)
        // Index 6 is the scattered Pomeron target (diffractive recoil proton)
        TLorentzVector pGamma = event->particles[2].p;
        TLorentzVector pPom   = event->particles[6].p;

        // Assign Event-level scalars
        iEvent_val = event->eventNumber;
        t_val      = event->t;
        Q2_val     = event->Q2;
        W_val      = event->W;
        x_val      = event->x;
        y_val      = event->y;
        s_val      = event->s;
        xpom_val   = event->xpom;
        pol_val    = (event->polarization == transverse) ? 0 : 1;
        dmode_val  = (event->diffractiveMode == coherent) ? 0 : 1;

        // J/psi kinematic scalars
        jpsi_px  = vm.Px();
        jpsi_py  = vm.Py();
        jpsi_pz  = vm.Pz();
        jpsi_E   = vm.E();
        jpsi_pt  = vm.Pt();
        jpsi_eta = vm.Eta();
        jpsi_phi = vm.Phi();
        jpsi_m   = vm.M();
        jpsi_y   = vm.Rapidity();

        // Electron (e-) kinematics
        em_px  = d1.Px();
        em_py  = d1.Py();
        em_pz  = d1.Pz();
        em_E   = d1.E();
        em_pt  = d1.Pt();
        em_eta = d1.Eta();
        em_phi = d1.Phi();
        em_m   = d1.M();

        // Positron (e+) kinematics
        ep_px  = d2.Px();
        ep_py  = d2.Py();
        ep_pz  = d2.Pz();
        ep_E   = d2.E();
        ep_pt  = d2.Pt();
        ep_eta = d2.Eta();
        ep_phi = d2.Phi();
        ep_m   = d2.M();

        // Reconstructed dielectron pair kinematics
        TLorentzVector pair = d1 + d2;
        pair_m   = pair.M();
        pair_pt  = pair.Pt();
        pair_y   = pair.Rapidity();
        pair_eta = pair.Eta();

        // Photon-emitting proton kinematics
        p_gamma_px  = pGamma.Px();
        p_gamma_py  = pGamma.Py();
        p_gamma_pz  = pGamma.Pz();
        p_gamma_E   = pGamma.E();
        p_gamma_pt  = pGamma.Pt();
        p_gamma_eta = (p_gamma_pt > 1e-6) ? pGamma.Eta() : 999.0;
        p_gamma_phi = pGamma.Phi();
        p_gamma_m   = pGamma.M();

        // Pomeron-target proton kinematics
        p_pom_px  = pPom.Px();
        p_pom_py  = pPom.Py();
        p_pom_pz  = pPom.Pz();
        p_pom_E   = pPom.E();
        p_pom_pt  = pPom.Pt();
        p_pom_eta = (p_pom_pt > 1e-6) ? pPom.Eta() : 999.0;
        p_pom_phi = pPom.Phi();
        p_pom_m   = pPom.M();

        // Missing transverse momentum calculations:
        // 1. Missing pT relative to the Pomeron target proton (tagged by Roman Pots):
        //    pT_miss,pom = |vec(pT_J/psi) + vec(pT_p_pom)|
        double miss_px_pom = vm.Px() + pPom.Px();
        double miss_py_pom = vm.Py() + pPom.Py();
        pt_missing_pom = std::sqrt(miss_px_pom * miss_px_pom + miss_py_pom * miss_py_pom);

        // 2. Missing pT relative to the photon-emitting proton:
        //    pT_miss,gamma = |vec(pT_J/psi) + vec(pT_p_gamma)|
        double miss_px_gam = vm.Px() + pGamma.Px();
        double miss_py_gam = vm.Py() + pGamma.Py();
        pt_missing_gamma = std::sqrt(miss_px_gam * miss_px_gam + miss_py_gam * miss_py_gam);

        // 3. Global transverse momentum balance (four-momentum conservation check):
        //    pT_balance = |vec(pT_J/psi) + vec(pT_p_pom) + vec(pT_p_gamma)|  == 0
        double bal_px = vm.Px() + pPom.Px() + pGamma.Px();
        double bal_py = vm.Py() + pPom.Py() + pGamma.Py();
        pt_balance = std::sqrt(bal_px * bal_px + bal_py * bal_py);

        // Append record to TTree
        tree->Fill();
        nValidEvents++;

        // Progress logging
        if ((iEvt + 1) % printInterval == 0) {
            cout << "Processed " << (iEvt + 1) << " / " << nEventsRequested 
                 << " events (" << (100.0 * (iEvt + 1) / nEventsRequested) << "%)..." << endl;
        }
    }

    // Determine the integrated cross section in nanobarns
    double totalCrossSection_nb = (cmdCrossSection > 0.0) ? cmdCrossSection : sartre.totalCrossSection();
    cout << "Finished event generation." << endl;
    cout << "Total Valid Events:         " << nValidEvents << endl;
    cout << "Sartre Total Cross Section: " << totalCrossSection_nb << " nb" << endl;

    // =========================================================================
    // CROSS-SECTION & NORMALIZATION METADATA HISTOGRAM
    // =========================================================================
    // Bin 1: Total integrated cross section sigma_total in nb
    // Bin 2: Number of valid simulated events (for luminosity / weight calculation)
    TH1D* hSummary = new TH1D("histoForCSandNumberOfEvents", "Cross section (nb) and event count", 2, 0, 2);
    hSummary->SetBinContent(1, totalCrossSection_nb);
    hSummary->SetBinContent(2, (double)nValidEvents);
    hSummary->GetXaxis()->SetBinLabel(1, "sigma_total_nb");
    hSummary->GetXaxis()->SetBinLabel(2, "nEvents");

    // Persist tree and summary histogram to ROOT file
    tree->Write();
    hSummary->Write();
    outFile->Close();

    cout << "Successfully written ROOT file: " << rootfile << endl;
    return 0;
}
