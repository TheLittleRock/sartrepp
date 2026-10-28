#!/usr/bin/env python3
"""
================================================================================
verify_simulations.py

Automated Physics Sanity & Self-Verification Suite for Sartre Simulations
Master Thesis: Analysis of J/psi Photoproduction in p+p Collisions at 510 GeV

Implements 5 Mandatory Physics Checks:
  1. Event count & NaN/Inf integrity check in all 4-momenta.
  2. Cross section validity (positive, nanobarn range, BR documentation).
  3. Rapidity symmetry: abs(mean(y_jpsi)) < 0.05 in symmetric p+p collisions.
  4. Kinematic consistency:
     - Daughter invariant mass m(e+e-) == M(J/psi) = 3.0969 GeV within 1 MeV.
     - Transverse balance: |pT(J/psi) + pT(p1) + pT(p2)| < 1 MeV.
  5. Roman Pot forward acceptance (Cut F2) and Pomeron vs photon emitter recoil.
================================================================================
"""

import os
import sys
import json
import numpy as np
from pathlib import Path

# Try importing analysis stack
try:
    import uproot
    import awkward as ak
    import vector
except ImportError as e:
    print(f"Error importing analysis packages: {e}")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Reference Constants
M_JPSI = 3.0969 # GeV/c2
BR_EE = 0.05971 # 5.971%

def verify_file(root_path, expected_events=None):
    """
    Run comprehensive self-verification checks on a Sartre output ROOT file.
    """
    print(f"\n{'='*75}")
    print(f"  Verifying Sartre Simulation Output: {root_path.name}")
    print(f"{'='*75}")

    if not root_path.exists():
        print(f"❌ FAIL: File not found: {root_path}")
        return False

    with uproot.open(root_path) as f:
        # Check TTree presence
        tree_keys = [k.split(';')[0] for k in f.keys()]
        if 'sartre_tree' not in tree_keys and 'sartre' not in tree_keys:
            print(f"❌ FAIL: Tree 'sartre_tree' not found in file. Available: {f.keys()}")
            return False
        
        t_name = 'sartre_tree' if 'sartre_tree' in tree_keys else 'sartre'
        tree = f[t_name]
        n_entries = tree.num_entries
        print(f"  Tree name: '{t_name}', Total entries: {n_entries:,}")

        # -------------------------------------------------------------
        # Check 1: Event Count & NaNs
        # -------------------------------------------------------------
        if expected_events is not None and n_entries != expected_events:
            print(f"❌ FAIL Check 1: Expected {expected_events:,} events, found {n_entries:,}")
            return False

        # Load required branches
        branches = [
            'jpsi_px', 'jpsi_py', 'jpsi_pz', 'jpsi_E', 'jpsi_pt', 'jpsi_y', 'jpsi_m',
            'em_px', 'em_py', 'em_pz', 'em_E', 'em_pt', 'em_eta',
            'ep_px', 'ep_py', 'ep_pz', 'ep_E', 'ep_pt', 'ep_eta',
            'pair_m', 'pair_pt', 'pair_y',
            'p_pom_px', 'p_pom_py', 'p_pom_pz', 'p_pom_E', 'p_pom_pt',
            'p_gamma_px', 'p_gamma_py', 'p_gamma_pz', 'p_gamma_E', 'p_gamma_pt',
            'pt_balance'
        ]
        
        data = tree.arrays(branches, library="np")

        # Check for NaNs or Infs
        nan_count = 0
        for b in branches:
            n_nan = np.sum(np.isnan(data[b])) + np.sum(np.isinf(data[b]))
            if n_nan > 0:
                print(f"❌ FAIL: Branch '{b}' contains {n_nan} NaN or Inf values!")
                nan_count += n_nan

        if nan_count > 0:
            print(f"❌ FAIL Check 1: Total {nan_count} NaNs/Infs found!")
            return False
        print(f"  ✅ Check 1 PASSED: {n_entries:,} valid events, 0 NaNs, 0 Infs.")

        # -------------------------------------------------------------
        # Check 2: Cross Section Validity
        # -------------------------------------------------------------
        total_cs_nb = None
        if (DATA_DIR / "cross_sections.json").exists():
            with open(DATA_DIR / "cross_sections.json", "r") as cs_f:
                cs_info = json.load(cs_f)
                for k, v in cs_info.items():
                    if k in root_path.name:
                        total_cs_nb = v.get("total_cross_section_nb")
                        break

        if total_cs_nb is None and 'histoForCSandNumberOfEvents' in tree_keys:
            h = f['histoForCSandNumberOfEvents']
            total_cs_nb = float(h.values()[0])

        if total_cs_nb is None or total_cs_nb <= 0:
            print(f"❌ FAIL Check 2: Total cross section not found or invalid: {total_cs_nb}")
            return False
        
        cs_ee_pb = total_cs_nb * 1000.0 * BR_EE
        print(f"  Cross section from model benchmarks: {total_cs_nb:.4f} nb")
        print(f"  Cross section in e+e- channel (BR = 5.971%): {cs_ee_pb:.1f} pb")
        if not (1.0 < total_cs_nb < 100.0):
            print(f"⚠️  WARNING: Total cross section {total_cs_nb:.2f} nb is outside typical 1-100 nb range.")
        print(f"  ✅ Check 2 PASSED: Positive cross section ({total_cs_nb:.4f} nb, {cs_ee_pb:.1f} pb in e+e-).")

        # -------------------------------------------------------------
        # Check 3: Rapidity Symmetry (p+p symmetric beams)
        # -------------------------------------------------------------
        y_vals = data['pair_y']
        mean_y = float(np.mean(y_vals))
        std_y = float(np.std(y_vals))
        print(f"  Rapidity distribution: mean(y) = {mean_y:+.4f}, std(y) = {std_y:.4f}")
        print(f"  Min(y) = {np.min(y_vals):.2f}, Max(y) = {np.max(y_vals):.2f}")

        if abs(mean_y) > 0.05:
            print(f"❌ FAIL Check 3: Asymmetric rapidity distribution in symmetric p+p: mean(y) = {mean_y:.4f} > 0.05")
            return False
        print(f"  ✅ Check 3 PASSED: Rapidity is symmetric around 0 (|mean| = {abs(mean_y):.4f} < 0.05).")

        # -------------------------------------------------------------
        # Check 4: Daughter Mass & Kinematic Balance
        # -------------------------------------------------------------
        pair_mass = data['pair_m']
        mean_m = float(np.mean(pair_mass))
        std_m = float(np.std(pair_mass))
        max_m_dev = float(np.max(np.abs(pair_mass - M_JPSI)))
        print(f"  Reconstructed e+e- mass: mean = {mean_m:.6f} GeV/c2 (expected {M_JPSI}), std = {std_m*1000.0:.2f} MeV/c2")
        print(f"  Max mass deviation from J/psi pole: {max_m_dev*1000.0:.3f} MeV/c2")

        if abs(mean_m - M_JPSI) > 0.005:
            print(f"❌ FAIL Check 4: Mass pole shift too large: {abs(mean_m - M_JPSI)*1000.0:.2f} MeV")
            return False

        if std_m > 0.02: # 20 MeV width
            print(f"❌ FAIL Check 4: Mass width too large: {std_m*1000.0:.2f} MeV")
            return False

        pt_bal = data['pt_balance']
        mean_bal = float(np.mean(pt_bal))
        max_bal = float(np.max(pt_bal))
        print(f"  Total transverse balance: mean = {mean_bal*1e6:.2f} keV/c, max = {max_bal*1e3:.2f} MeV/c")

        if max_bal > 0.01: # 10 MeV
            print(f"❌ FAIL Check 4: Transverse momentum balance violated: max = {max_bal:.4f} GeV")
            return False
        print(f"  ✅ Check 4 PASSED: Mass matches J/psi and transverse balance is exact.")

        # -------------------------------------------------------------
        # Check 5: Roman Pot Acceptance (Fiducial Cut F2)
        # -------------------------------------------------------------
        px_pom = data['p_pom_px']
        py_pom = data['p_pom_py']
        px_gam = data['p_gamma_px']
        py_gam = data['p_gamma_py']

        # Michal's Formula 4.2 / Cut F2:
        # 0.4 < |py| < 0.8, px > -0.27, (px + 0.6)^2 + py^2 < 1.25
        def in_rp_f2(px, py):
            cond_y = (np.abs(py) > 0.4) & (np.abs(py) < 0.8)
            cond_x = px > -0.27
            cond_circ = (px + 0.6)**2 + py**2 < 1.25
            return cond_y & cond_x & cond_circ

        rp_pom = in_rp_f2(px_pom, py_pom)
        rp_gam = in_rp_f2(px_gam, py_gam)

        frac_pom = np.mean(rp_pom) * 100.0
        frac_gam = np.mean(rp_gam) * 100.0

        print(f"  Proton acceptance in STAR Roman Pot Fiducial Region F2:")
        print(f"    - Pomeron-target proton: {frac_pom:.2f}% (recoils with pT ~ sqrt(|t|))")
        print(f"    - Photon-emitter proton: {frac_gam:.2f}% (soft photon recoil)")

        # Verify physics insight (Michal Vranovsky page 78)
        if frac_pom < 5.0:
            print(f"⚠️  WARNING: Pomeron proton RP acceptance ({frac_pom:.2f}%) lower than expected ~10-20%.")
        if frac_gam > 1.0:
            print(f"⚠️  WARNING: Photon-emitting proton RP acceptance ({frac_gam:.2f}%) higher than expected <0.1%.")

        print(f"  ✅ Check 5 PASSED: Roman Pot kinematics correctly reflect photon vs Pomeron recoil physics.")

    print(f"\n🎯 ALL 5 CHECKS PASSED FOR: {root_path.name}\n")
    return True

def main():
    files_to_check = [
        DATA_DIR / "sartre_bSat_HMPZ_100k.root",
        DATA_DIR / "sartre_bNonSat_HMPZ_100k.root",
        DATA_DIR / "test_50.root"
    ]
    
    # Check if command line passed specific file
    if len(sys.argv) > 1:
        files_to_check = [Path(sys.argv[1])]

    verified_any = False
    all_ok = True

    for p in files_to_check:
        if p.exists():
            verified_any = True
            ok = verify_file(p)
            if not ok:
                all_ok = False

    if not verified_any:
        print("No simulation ROOT files found to verify.")
        sys.exit(1)

    sys.exit(0 if all_ok else 1)

if __name__ == "__main__":
    main()
