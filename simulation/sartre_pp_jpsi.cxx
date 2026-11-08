//==============================================================================
//  sartre_pp_jpsi.cxx
//  Monte Carlo Simulation Driver for Exclusive J/psi Photoproduction in p+p
//  Reaction: p + p -> p + J/psi + p (with J/psi -> e+ e-) at sqrt(s) = 510 GeV
//==============================================================================

#include <iostream>
#include <cmath>
#include <string>
#include <utility>

// ROOT headers
#include "TFile.h"
#include "TTree.h"
#include "TH1D.h"
#include "TLorentzVector.h"
#include "TRandom3.h"

// Sartre 2 headers
#include "Sartre.h"
#include "Settings.h"
#include "Event.h"
#include "TwoBodyVectorMesonDecay.h"

using namespace std;

//------------------------------------------------------------------------------
// Helper Struct: ParticleBranch
// Purpose: Avoids declaring 9 separate doubles and 9 tree->Branch() calls for
//          every single particle. Creates the exact same flat branches in the
//          ROOT TTree (e.g., "jpsi_px", "jpsi_pt", etc.) automatically.
//------------------------------------------------------------------------------
struct ParticleBranch {
    double px = 0, py = 0, pz = 0, E = 0;
    double pt = 0, eta = 0, phi = 0, m = 0, y = 0;

    // Register branches in the TTree with a given prefix (e.g. "jpsi", "em")
    void bindToTree(TTree* tree, const string& prefix, bool includeRapidity = false) {
        tree->Branch((prefix + "_px").c_str(),  &px,  (prefix + "_px/D").c_str());
        tree->Branch((prefix + "_py").c_str(),  &py,  (prefix + "_py/D").c_str());
        tree->Branch((prefix + "_pz").c_str(),  &pz,  (prefix + "_pz/D").c_str());
        tree->Branch((prefix + "_E").c_str(),   &E,   (prefix + "_E/D").c_str());
        tree->Branch((prefix + "_pt").c_str(),  &pt,  (prefix + "_pt/D").c_str());
        tree->Branch((prefix + "_eta").c_str(), &eta, (prefix + "_eta/D").c_str());
        tree->Branch((prefix + "_phi").c_str(), &phi, (prefix + "_phi/D").c_str());
        tree->Branch((prefix + "_m").c_str(),   &m,   (prefix + "_m/D").c_str());
        if (includeRapidity) {
            tree->Branch((prefix + "_y").c_str(), &y, (prefix + "_y/D").c_str());
        }
    }

    // Extract kinematics from a ROOT TLorentzVector
    void fillFrom(const TLorentzVector& v) {
        px  = v.Px();
        py  = v.Py();
        pz  = v.Pz();
        E   = v.E();
        pt  = v.Pt();
        // Protect against division-by-zero in pseudorapidity when pT is ~0
        eta = (pt > 1e-6) ? v.Eta() : 999.0;
        phi = v.Phi();
        m   = v.M();
        y   = v.Rapidity();
    }
};

//------------------------------------------------------------------------------
// Function: applyRandomBeamReversal
// Purpose:  Sartre assumes asymmetric collisions where Beam 1 (+z) ALWAYS emits
//           the photon and Beam 2 (-z) is ALWAYS the Pomeron target.
//           In symmetric p+p collisions, either proton has a 50% chance to emit
//           the photon. We restore this symmetry by randomly rotating 50% of
//           the events by 180 degrees (pi radians) around the x-axis, which
//           flips Pz -> -Pz (rapidity y -> -y) and Py -> -Py.
//------------------------------------------------------------------------------
bool applyRandomBeamReversal(Event* event) {
    TRandom3* rnd = EventGeneratorSettings::randomGenerator();
    if (rnd->Uniform(1.0) > 0.5) {
        for (size_t i = 0; i < event->particles.size(); ++i) {
            event->particles[i].p.RotateX(M_PI);
        }
        return true;
    }
    return false;
}

//------------------------------------------------------------------------------
// Main Simulation Driver
//------------------------------------------------------------------------------
int main(int argc, char* argv[]) {
    // 1. Parse Command-Line Arguments
    // Only <runcard.txt> is required. Everything else is optional and overrides
    // the settings inside the runcard (used when running parallel worker chunks).
    if (argc < 2 || argc > 6) {
        cout << "Usage: " << argv[0] << " <runcard.txt> [output.root] [nEvents] [seed] [known_cs_nb]\n";
        return 1;
    }

    string runcard          = argv[1];
    string rootfile         = (argc >= 3) ? argv[2] : "";
    unsigned long cmdEvents = (argc >= 4) ? stoul(argv[3]) : 0;
    unsigned int  cmdSeed   = (argc >= 5) ? stoul(argv[4]) : 0;
    double cmdCrossSection  = (argc >= 6) ? stod(argv[5])  : 0.0;

    // 2. Initialize Sartre with the runcard
    Sartre sartre;
    if (!sartre.init(runcard)) {
        cerr << "ERROR: Sartre failed to initialize runcard: " << runcard << endl;
        return 1;
    }

    EventGeneratorSettings* settings = sartre.runSettings();

    // Apply command-line overrides (if provided by the parallel Python runner)
    if (cmdSeed > 0) {
        settings->setSeed(cmdSeed);
        EventGeneratorSettings::randomGenerator()->SetSeed(cmdSeed);
    }
    if (rootfile.empty()) rootfile = settings->rootfile();
    if (rootfile.empty()) rootfile = "sartre_out.root";

    unsigned long nEventsRequested = (cmdEvents > 0) ? cmdEvents : settings->numberOfEvents();

    // Read decay daughter PDG ID from runcard's `userInt` (default to 11 = electron)
    int daughterID = (settings->userInt() != 0) ? settings->userInt() : 11;

    cout << "==========================================================\n"
         << "  Runcard:          " << runcard << "\n"
         << "  Output ROOT file: " << rootfile << "\n"
         << "  Events to run:    " << nEventsRequested << "\n"
         << "  Decay PDG ID:     " << daughterID << "\n"
         << "==========================================================" << endl;

    // 3. Create Output ROOT File and TTree
    TFile* outFile = new TFile(rootfile.c_str(), "RECREATE");
    if (!outFile || outFile->IsZombie()) {
        cerr << "ERROR: Cannot create output ROOT file: " << rootfile << endl;
        return 1;
    }

    TTree* tree = new TTree("sartre_tree", "Sartre Exclusive J/psi Photoproduction in p+p");

    // Event-level kinematic variables
    int    iEvent_val = 0, pol_val = 0, dmode_val = 0, is_reversed = 0;
    double t_val = 0, Q2_val = 0, W_val = 0, x_val = 0, y_val = 0, s_val = 0, xpom_val = 0;

    tree->Branch("iEvent",      &iEvent_val,  "iEvent/I");
    tree->Branch("t",           &t_val,       "t/D");        // Momentum transfer squared at proton vertex (GeV^2)
    tree->Branch("Q2",          &Q2_val,      "Q2/D");       // Photon virtuality (GeV^2)
    tree->Branch("W",           &W_val,       "W/D");        // Photon-proton center-of-mass energy (GeV)
    tree->Branch("x",           &x_val,       "x/D");        // Bjorken-x
    tree->Branch("y",           &y_val,       "y/D");        // Photon inelasticity
    tree->Branch("s",           &s_val,       "s/D");        // Total p+p center-of-mass energy squared (GeV^2)
    tree->Branch("xpom",        &xpom_val,    "xpom/D");     // Pomeron momentum fraction
    tree->Branch("pol",         &pol_val,     "pol/I");      // Photon polarization: 0 = T, 1 = L
    tree->Branch("dmode",       &dmode_val,   "dmode/I");    // Diffractive mode: 0 = coherent, 1 = incoherent
    tree->Branch("is_reversed", &is_reversed, "is_reversed/I"); // 1 if beams were flipped (+z <-> -z)

    // Particle branches using our helper struct
    ParticleBranch b_jpsi, b_em, b_ep, b_p_gamma, b_p_pom;
    b_jpsi.bindToTree(tree,    "jpsi",    true);  // J/psi (includes rapidity jpsi_y)
    b_em.bindToTree(tree,      "em",      false); // Daughter electron (e-)
    b_ep.bindToTree(tree,      "ep",      false); // Daughter positron (e+)
    b_p_gamma.bindToTree(tree, "p_gamma", false); // Scattered proton that emitted the photon
    b_p_pom.bindToTree(tree,   "p_pom",   false); // Scattered proton that exchanged the Pomeron

    // Reconstructed e+e- pair and transverse momentum balance variables
    double pair_m = 0, pair_pt = 0, pair_y = 0, pair_eta = 0;
    double pt_missing_pom = 0, pt_missing_gamma = 0, pt_balance = 0;

    tree->Branch("pair_m",           &pair_m,           "pair_m/D");
    tree->Branch("pair_pt",          &pair_pt,          "pair_pt/D");
    tree->Branch("pair_y",           &pair_y,           "pair_y/D");
    tree->Branch("pair_eta",         &pair_eta,         "pair_eta/D");
    tree->Branch("pt_missing_pom",   &pt_missing_pom,   "pt_missing_pom/D");
    tree->Branch("pt_missing_gamma", &pt_missing_gamma, "pt_missing_gamma/D");
    tree->Branch("pt_balance",       &pt_balance,       "pt_balance/D");

    // 4. Main Event Generation Loop
    TwoBodyVectorMesonDecay decayEngine;
    unsigned long nValidEvents = 0;
    unsigned long printStep = max(1UL, min(100UL, nEventsRequested / 100));

    // How Sartre's `event->particles` array is structured:
    //   Index 0: Incoming Beam 1 proton (+z)
    //   Index 1: Incoming Beam 2 proton (-z)
    //   Index 2: Outgoing proton from photon vertex (very small pT, stays in beam pipe)
    //   Index 3: Virtual photon (gamma*)
    //   Index 4: Produced Vector Meson (J/psi)
    //   Index 5: Pomeron (IP)
    //   Index 6: Outgoing proton from Pomeron vertex (higher pT, measured in Roman Pots)
    for (unsigned long iEvt = 0; iEvt < nEventsRequested; ++iEvt) {
        Event* event = sartre.generateEvent();
        if (!event) continue;

        // Symmetrize identical p+p beams (50% chance to flip z-axis)
        bool rev = (settings->UPC() && settings->A() == settings->UPCA())
                   ? applyRandomBeamReversal(event) : false;

        TLorentzVector vm     = event->particles[4].p; // J/psi
        TLorentzVector pGamma = event->particles[2].p; // Photon-emitting proton
        TLorentzVector pPom   = event->particles[6].p; // Pomeron-target proton

        // Sanity check: skip event if J/psi 4-momentum has NaN or negative energy
        if (vm.E() <= 0 || vm.M() <= 0 || !isfinite(vm.E())) continue;

        // Decay J/psi -> e- (d1) + e+ (d2) preserving helicity polarization
        pair<TLorentzVector, TLorentzVector> daughters = decayEngine.decayVectorMeson(vm, *event, daughterID);
        TLorentzVector d1   = daughters.first;
        TLorentzVector d2   = daughters.second;
        TLorentzVector pair = d1 + d2;

        // Fill event-level variables
        iEvent_val  = event->eventNumber;
        t_val       = event->t;
        Q2_val      = event->Q2;
        W_val       = event->W;
        x_val       = event->x;
        y_val       = event->y;
        s_val       = event->s;
        xpom_val    = event->xpom;
        pol_val     = (event->polarization == transverse) ? 0 : 1;
        dmode_val   = (event->diffractiveMode == coherent) ? 0 : 1;
        is_reversed = rev ? 1 : 0;

        // Fill particle kinematics using our helper struct
        b_jpsi.fillFrom(vm);
        b_em.fillFrom(d1);
        b_ep.fillFrom(d2);
        b_p_gamma.fillFrom(pGamma);
        b_p_pom.fillFrom(pPom);

        // Fill reconstructed pair kinematics
        pair_m   = pair.M();
        pair_pt  = pair.Pt();
        pair_y   = pair.Rapidity();
        pair_eta = pair.Eta();

        // Fill transverse momentum balance checks:
        // In an exclusive reaction p+p -> p + J/psi + p, total transverse momentum is zero:
        //   vec(pT_J/psi) + vec(pT_p_pom) + vec(pT_p_gamma) = 0
        // If only the Roman Pot proton (p_pom) is detected, the missing pT equals p_gamma's pT:
        pt_missing_pom   = (vm + pPom).Pt();
        pt_missing_gamma = (vm + pGamma).Pt();
        pt_balance       = (vm + pPom + pGamma).Pt(); // Should be ~0 (numerical precision check)

        tree->Fill();
        nValidEvents++;

        if ((iEvt + 1) % printStep == 0 || (iEvt + 1) == nEventsRequested) {
            cout << "Processed " << (iEvt + 1) << " / " << nEventsRequested << " events..." << endl;
        }
    }

    // 5. Compute or Use Precomputed Total Cross Section (known_cs_nb)
    // If a known cross section was explicitly provided via argv[5] (cmdCrossSection > 0.0),
    // use it directly. Otherwise, compute it dynamically via Sartre's totalCrossSection().
    double totalCrossSection_nb = 0.0;
    if (cmdCrossSection > 0.0) {
        totalCrossSection_nb = cmdCrossSection;
    } else {
        cout << "Calculating total cross section via Sartre phase-space integration..." << endl;
        totalCrossSection_nb = sartre.totalCrossSection();
    }

    cout << "Finished! Valid Events: " << nValidEvents
         << " | Cross Section: " << totalCrossSection_nb << " nb\n";

    // 6. Save Metadata Histogram (Cross Section & Event Count)
    // NOTE ON PARALLEL MERGING (`hadd`):
    // When `hadd` merges N worker files, it sums the bins of all histograms!
    //   - Bin 2 (nEvents) will correctly equal the sum of all events across all workers.
    //   - Bin 1 (sigma_total_nb) will be summed N times (N_workers * sigma_total_nb)!
    TH1D* hSummary = new TH1D("histoForCSandNumberOfEvents", "Cross section (nb) and event count", 2, 0, 2);
    hSummary->SetBinContent(1, totalCrossSection_nb);
    hSummary->SetBinContent(2, (double)nValidEvents);
    hSummary->GetXaxis()->SetBinLabel(1, "sigma_total_nb");
    hSummary->GetXaxis()->SetBinLabel(2, "nEvents");

    tree->Write();
    hSummary->Write();
    outFile->Close();

    return 0;
}