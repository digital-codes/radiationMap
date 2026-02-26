
import datetime
import numpy as np
import json
from pathlib import Path
import gzip
import matplotlib.pyplot as plt

import sys

if len(sys.argv) < 2:
    print("Usage: python npz2png.py <input_npz_file>")
    exit()
    

windData = np.load(sys.argv[1])
u_data = windData["u"]
u_mask = windData["u_mask"]
v_data = windData["v"]
v_mask = windData["v_mask"]
lats = windData["lats"]
lons = windData["lons"]
speed = windData["speed"]
speed_mask = windData["speed_mask"]



# Create a combined valid-data mask and masked arrays
mask_all = u_mask | v_mask | speed_mask | np.isnan(u_data) | np.isnan(v_data) | np.isnan(speed)
u_ma = np.ma.array(u_data, mask=mask_all)
v_ma = np.ma.array(v_data, mask=mask_all)
speed_ma = np.ma.array(speed, mask=mask_all)

# Decimate the grid for barbs so the plot is legible
ny, nx = u_ma.shape
target_points = 90  # target number of points along long axis
step_x = max(1, nx // target_points)
step_y = max(1, ny // target_points)

lons_s = lons[::step_y, ::step_x]
lats_s = lats[::step_y, ::step_x]
u_s = u_ma[::step_y, ::step_x]
v_s = v_ma[::step_y, ::step_x]

# Create figure: background is wind speed, overlay barbs
fig, ax = plt.subplots(figsize=(16, 8))  # ration is 2 : 1
# pcm = ax.pcolormesh(lons, lats, speed_ma, shading='auto', cmap='viridis') 

#cb = fig.colorbar(pcm, ax=ax, label='Wind speed (m/s)')
# remove side colorbar (if created) and make the axes fill the full figure

fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
ax.set_position([0.0, 0.0, 1.0, 1.0])



# add a small color scale inside the plot area (not on any external side)
#cax = inset_axes(ax, width="3%", height="30%", loc='upper right',
#                 bbox_to_anchor=(0.98, 0.98), bbox_transform=ax.transAxes, borderpad=0)
#fig.colorbar(pcm, cax=cax, orientation='vertical', label='Wind speed (m/s)')
# make the inset colorbar visually subtle so it doesn't reduce usable plot area too much
#cax.yaxis.set_label_position('right')
#cax.yaxis.tick_right()

# Plot barbs
ax.barbs(lons_s, lats_s, u_s, v_s, length=6, linewidth=0.4, pivot='middle', color='k')

ax.set_xlabel('Longitude')
ax.set_ylabel('Latitude')
ax.set_title('100 m wind speed and barbs')
ax.set_xlim(np.nanmin(lons), np.nanmax(lons))
ax.set_ylim(np.nanmin(lats), np.nanmax(lats))
plt.tight_layout()

figname = "wind.png"
plt.savefig(figname, dpi=300)
plt.close(fig)

print(f"Wrote windbarb image to {figname}")
