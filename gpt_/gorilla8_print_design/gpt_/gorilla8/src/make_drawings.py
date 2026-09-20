"""Dimensioned interface sheets and transparent first-order strength estimates."""
import os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).resolve().parents[2]/'.tools/mpl'))
import json,math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle,Rectangle
from matplotlib.backends.backend_pdf import PdfPages
from design import OUT,REPORTS,PALM_X_MIN_MM,PALM_X_MAX_MM,PALM_WIDTH_MM

def finish(ax,title):
    ax.set_aspect('equal');ax.set_title(title,fontsize=11,fontweight='bold');ax.grid(alpha=.15)
    ax.set_xlabel('mm');ax.set_ylabel('mm')

def flat_palm_strength(mass_kg):
    """Ideal rectangular sections, 45 mm heel and 9 mm toe load cases."""
    width,plate,rib_width,rib_height=PALM_WIDTH_MM,2.,4.,6.
    area=width*plate+2*rib_width*rib_height
    zbar=(width*plate*(-9)+2*rib_width*rib_height*(-5))/area
    inertia=width*plate**3/12+width*plate*(-9-zbar)**2
    inertia+=2*(rib_width*rib_height**3/12+rib_width*rib_height*(-5-zbar)**2)
    extreme=max(-2-zbar,zbar+10)
    force=mass_kg*9.81/2
    cases=[]
    for name,I,c,length in [('ribbed heel',inertia,extreme,-PALM_X_MIN_MM),
                            ('toe beyond rib end',width*3**3/12,1.5,PALM_X_MAX_MM-11)]:
        stress=force*length*c/I
        cases.append(dict(section=name,I_mm4=I,section_modulus_mm3=I/c,
                          load_per_palm_N=force,lever_mm=length,
                          nominal_bending_MPa=stress,screening_stress_MPa=6*stress,
                          screening_margin=8/(6*stress),
                          nominal_end_deflection_mm=force*length**3/(3*1000*I),
                          point_load_limit_for_assumed_screen_N=8*I/(6*length*c),
                          entire_weight_on_one_palm_screen_MPa=12*stress,
                          entire_weight_on_one_palm_screen_passed=12*stress<=8))
    return dict(mass_kg=mass_kg,load_case='two palms equally share gravity; load at sole extremity',
                rear_plate_mm=[width,plate],toe_plate_mm=[width,3],two_ribs_each_mm=[rib_width,rib_height],
                heel_centroid_z_mm=zbar,sections=cases,
                adhesive_strength_validated=False,
                single_palm_edge_load_covered=False,
                note='Not proof of transient, layer, rib-root, bolt-bearing or adhesive strength.')

def bridge_strength(mass_kg):
    force=mass_kg*9.81/2
    sections=[]
    for name,width in [('shoulder rectangular bridge',16.),('shoulder at inner-fork relief',14.)]:
        sections.append((name,width*13**3/12,6.5,27. if width==16 else 21.))
    sections.append(('hip bridge',8*6.2**3/12,3.1,21.))
    return [dict(section=name,I_mm4=I,section_modulus_mm3=I/c,span_mm=span,
                 reference_force_N=force,reference_case='half body gravity on one limb',
                 nominal_bending_MPa=force*span*c/I,
                 screening_stress_MPa=6*force*span*c/I,
                 screening_margin=8*I/(6*force*span*c),
                 point_load_limit_for_assumed_screen_N=8*I/(6*span*c),
                 nominal_end_deflection_mm=force*span**3/(3*1000*I),
                 scope='Vertical-load bending only; not bridge torsion, joint-local bearing or dynamic certification.')
            for name,I,c,span in sections]

def bridge_page(pdf,dest):
    fig,axes=plt.subplots(1,3,figsize=(16.5,8.27),layout='constrained')
    for ax,width,title in [(axes[0],16,'Shoulder: ordinary section'),(axes[1],14,'Shoulder: inner-fork relief section')]:
        ax.add_patch(Rectangle((-8.5,-28),width,13,facecolor='.78',edgecolor='black'))
        ax.set_xlim(-14,13);ax.set_ylim(-39,-7);finish(ax,title)
        ax.text(-13,-37,f'Width {width:g} x height 13\nZ=-28...-15; base X-Z coordinates\nContinuous full-height cup connection',fontsize=9)
    axes[1].text(-13,-12,'At |Y|=35...40:\nremove X=5.5...8.5, full height',fontsize=9)
    ax=axes[2]
    ax.add_patch(Rectangle((-13,-64),8,6.2,facecolor='.78',edgecolor='black'))
    ax.set_xlim(-18,9);ax.set_ylim(-73,-49);finish(ax,'Hip bridge: X-Z section')
    ax.text(-17,-71,'X=-13...-5; Z=-64...-57.8\nY=0...+/-52; outer span 21\nSection 8 x 6.2',fontsize=9)
    fig.suptitle('GORILLA8 / P01 integrated bridges / sections along Y / dimensions in mm',fontweight='bold')
    fig.text(.05,.035,'Shoulder root / relief screening spans: 27 / 21 mm. Central: X=-12...8.5, Y=+/-29, Z=-28...-15.\nCup interface at X=6.6: |Y|=41.5...56, Z=-28...-15, area 14.5 x 13. Full infill in every bridge and connection.',fontsize=10)
    pdf.savefig(fig);fig.savefig(dest/'bridge_interfaces.png',dpi=140);plt.close(fig)

def flat_palm_page(pdf,dest):
    fig,axes=plt.subplots(1,3,figsize=(16.5,8.27),layout='constrained')
    low,high,width=PALM_X_MIN_MM,PALM_X_MAX_MM,PALM_WIDTH_MM
    ax=axes[0]
    ax.add_patch(Rectangle((low,-width/2),high-low,width,fill=False,lw=2))
    for y in [-width/2,width/2-4]:
        ax.add_patch(Rectangle((low,y),11-low,4,facecolor='.82',edgecolor='.3'))
    for y in [-9,9]:
        ax.add_patch(Circle((0,y),3.4,fill=False,lw=1.5))
        ax.add_patch(Circle((0,y),1.15,fill=False))
        ax.add_patch(Circle((0,y),2.6,fill=False,ls='--'))
    ax.annotate('',xy=(low,22),xytext=(high,22),arrowprops=dict(arrowstyle='<->'))
    ax.text((low+high)/2,24,f'{high-low:g} total',ha='center')
    ax.set_xlim(low-7,high+9);ax.set_ylim(-32,31);finish(ax,'Flat palm: plan / X horizontal, Y vertical')
    ax.text(low-5,-29,'Width 34; 2 ribs 4 wide\n2 x D2.3 at (0,+/-9); bosses D6.8\nDashed D5.2: TPU service holes',fontsize=9)
    ax=axes[1]
    ax.add_patch(Rectangle((low,-12),high-low,2,facecolor='.25',edgecolor='black'))
    ax.add_patch(Rectangle((low,-10),high-low,2,facecolor='.75',edgecolor='black'))
    ax.add_patch(Rectangle((11,-8),high-11,1,facecolor='.75',edgecolor='black'))
    ax.add_patch(Rectangle((low,-8),11-low,6,facecolor='.87',edgecolor='black'))
    ax.axvline(0,ls=':',color='.4');ax.axhline(0,ls=':',color='.4')
    for z,label,label_z in [(-2,'rib top -2',4),(-7,'toe top -7',-3),(-10,'bond face -10',-9),(-12,'TPU bottom -12',-15)]:
        ax.annotate(label,xy=(11 if z==-2 else high,z),xytext=(high+4,label_z),fontsize=8,
                    arrowprops=dict(arrowstyle='-',lw=.5))
    ax.set_xlim(low-4,high+37);ax.set_ylim(-32,31);finish(ax,'Sole / rib side section (original palm omitted)')
    ax.text(low,-27,'Local origin: lower-link (0,0,-76)\nRear plate 2; toe 3; ribs 6 high; TPU 2\nRibs end at X=11; toe overhang 9',fontsize=9)
    ax=axes[2];ax.axis('off')
    ax.text(0,.93,'FRONT PALM ASSEMBLY',fontsize=12,fontweight='bold',va='top',transform=ax.transAxes)
    ax.text(0,.84,'2 x M2x20 + ordinary nuts + thin washers\nPETG head seat: Z=-9\nNut seat: Z=6.8; pocket AF4.1\nWasher ~0.3: screw tip Z=10.7\nHead height <=2.0: lowest head Z=-11.3',fontsize=10,linespacing=1.7,va='top',transform=ax.transAxes)
    ax.text(0,.50,'TPU D5.2 holes are through service holes.\nThe screws DO NOT clamp the front TPU.\nBond the whole TPU face with a compatible\nflexible adhesive after a real coupon test.\nKeep service holes and screw heads clear.',fontsize=10,linespacing=1.7,va='top',transform=ax.transAxes)
    ax.text(0,.20,'Adhesive thickness is not in CAD.\nMeasure assembled height and planarity.\nRear round pads remain mechanically clamped.\nDimensions in mm; schematic, do not scale.',fontsize=9,linespacing=1.7,va='top',transform=ax.transAxes)
    fig.suptitle('GORILLA8 / Flat front palm manufacturing interfaces',fontweight='bold')
    pdf.savefig(fig);fig.savefig(dest/'flat_palm_interfaces.png',dpi=140);plt.close(fig)

def main():
    dest=OUT/'drawings';dest.mkdir(exist_ok=True)
    with PdfPages(dest/'interfaces.pdf') as pdf:
        fig,axes=plt.subplots(1,3,figsize=(16.5,8.27),layout='constrained')
        ax=axes[0];ax.add_patch(Circle((0,0),10.5,fill=False,lw=2));ax.add_patch(Circle((0,0),8,fill=False,ls='--'))
        ax.add_patch(Circle((0,0),3.6,fill=False,lw=1.3))
        for x,z in [(6,0),(-6,0),(0,6),(0,-6)]:ax.add_patch(Circle((x,z),1.15,fill=False))
        ax.set_xlim(-15,15);ax.set_ylim(-16,16);finish(ax,'Rotor interface (look along Y)')
        ax.text(-14,-14,'4 x D2.3 on PCD12\nTool hole D7.2\nBoss OD16 / plate OD21',fontsize=9)
        ax=axes[1]
        for sign in [-1,1]:
            ax.add_patch(Rectangle((14.5 if sign>0 else -17,-8),2.5,16,fill=False,lw=2))
            ax.add_patch(Rectangle((17 if sign>0 else -20,-10.5),3,21,fill=False,lw=2))
        ax.annotate('',xy=(-14.5,13),xytext=(14.5,13),arrowprops=dict(arrowstyle='<->'))
        ax.text(0,14,'29.0 horn-face separation',ha='center',fontsize=9)
        ax.set_xlim(-24,24);ax.set_ylim(-17,18);finish(ax,'Fork section (Y horizontal / Z vertical)')
        ax.text(-23,-16,'2.5 stand-off + 3.0 plate = 5.5 grip\nST2x8: 2.5 nominal entry; max 3.0',fontsize=9)
        ax=axes[2];ax.add_patch(Rectangle((-13.4,-28),26.8,13,fill=False,lw=2))
        for x in [-8,8]:
            ax.add_patch(Circle((x,-22.5),1.15,fill=False));ax.add_patch(Circle((x,-22.5),2.1,fill=False,ls='--'))
        ax.annotate('',xy=(-8,-12),xytext=(8,-12),arrowprops=dict(arrowstyle='<->'));ax.text(0,-11,'16.0',ha='center')
        ax.set_xlim(-18,18);ax.set_ylim(-36,-7);finish(ax,'Stator saddle: lower hole row')
        ax.text(-17,-34,'X = +/-8; Z = -22.5\nD2.3 through; D4.2 x 1.0 counterbore\n3.0 wall - 1.0 recess = 2.0 grip',fontsize=9)
        fig.suptitle('GORILLA8 / Mechanical interfaces / dimensions in mm / do not scale drawing',fontweight='bold')
        pdf.savefig(fig);fig.savefig(dest/'interfaces.png',dpi=140);plt.close(fig)
        flat_palm_page(pdf,dest)
        bridge_page(pdf,dest)
        data=json.loads((REPORTS/'print_parts.json').read_text())
        fig,ax=plt.subplots(figsize=(11.69,8.27));ax.axis('off')
        rows=[[r['name'],r['quantity'],r['material'],' x '.join(f'{v:.1f}' for v in r['print_bbox_mm']),f"{r['mass_full_solid_g']:.2f}"] for r in data]
        table=ax.table(cellText=rows,colLabels=['Part','Qty','Material','Print bounding box (mm)','Solid mass (g)'],loc='center',cellLoc='left',colWidths=[.29,.06,.11,.34,.14])
        table.auto_set_font_size(False);table.set_fontsize(9);table.scale(1,1.7)
        ax.set_title('GORILLA8 / Part and print-orientation schedule',fontweight='bold')
        ax.text(.01,.05,'STEP: assembly-local coordinates. STL: oriented and translated onto build plate.\nNominal dimensions only. Print C01/C02 first; do not drill or resize OEM motor holes.',fontsize=10)
        pdf.savefig(fig);plt.close(fig)
    # Deliberately separate arithmetic screening from material/assembly proof.
    torque=100.0 # N mm, 0.10 N m
    sections=[('upper side spine',6*9**3/12,4.5,50),
              ('fork slotted rails, both cheeks',6*(14**3-5**3)/12,7,38),
              ('lower hollow stem',(16*14**3-11*9**3)/12,7,40)]
    records=[]
    for name,I,c,L in sections:
        stress=torque*c/I
        records.append(dict(section=name,I_mm4=I,nominal_bending_MPa=stress,
                            screening_stress_MPa=stress*2*3,assumed_allowable_MPa=8.,
                            screening_margin=8/(stress*6),nominal_end_deflection_mm=torque*L**2/(2*1000*I)))
    mass_kg=json.loads((REPORTS/'cad_checks.json').read_text())['total_mass_kg']
    report=dict(method='Euler-Bernoulli idealized sections; NOT FEA or material certification',
                torque_nm=.10,stress_concentration_assumption=2,transient_multiplier_assumption=3,
                PETG_effective_E_assumed_MPa=1000,PETG_allowable_assumed_MPa=8,
                requires_full_infill_at_sections=True,sections=records,
                OEM_thread_pullout_validated=False,layer_adhesion_validated=False,
                horn_screw_nominal_shear_N=.10/(4*.006),printed_horn_edge_ligament_mm=.85,
                flat_palm=flat_palm_strength(mass_kg),torso_bridges=bridge_strength(mass_kg),
                actual_contact_load_audit='See reports/strength_actual_loads.json, generated separately by src/audit_strength.py from both final simulation results.',
                scope='Arithmetic screen only. Exact curves, print anisotropy, screws and OEM plastic threads need tests.')
    (REPORTS/'strength_screen.json').write_text(json.dumps(report,indent=2)+'\n')
    print(dest/'interfaces.pdf');print(json.dumps(records,indent=2))

if __name__=='__main__':main()
