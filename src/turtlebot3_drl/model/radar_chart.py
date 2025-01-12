import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

# sns.set()

def _scale_data(data, ranges):
    """scales data[1:] to ranges[0],
    """
    for d, (y1, y2) in zip(data[1:], ranges[1:]):
        assert (y1 <= d <= y2) or (y2 <= d <= y1)
    x1, x2 = ranges[0]
    d = data[0]
    sdata = [d]
    for d, (y1, y2) in zip(data[1:], ranges[1:]):
        sdata.append((d-y1) / (y2-y1)
                     * (x2 - x1) + x1)
    return sdata

class ComplexRadar():
    def __init__(self, fig, variables, ranges,
                 n_ordinate_levels=6):
        angles = np.arange(0, 360, 360./len(variables))

        axes = [fig.add_axes([0.1,0.1,0.9,0.9],polar=True, label = "axes{}".format(i)) for i in range(len(variables))]
        l, text = axes[0].set_thetagrids(angles, labels=variables)
        [txt.set_rotation(angle-90) for txt, angle in zip(text, angles)]
        for ax in axes[1:]:
            ax.patch.set_visible(False)
            ax.grid("off")
            ax.xaxis.set_visible(False)
            # ax.xaxis.set_xticks
        for i, ax in enumerate(axes):
            grid = np.linspace(*ranges[i],
                               num=n_ordinate_levels)
            gridlabel = ["{}".format(round(x,2))
                         for x in grid]
            gridlabel[0] = "" # clean up origin
            lines, ticks = ax.set_rgrids(grid, labels=gridlabel, angle=angles[i])
            for line in lines:
                line.set_zorder(1)
            for tick in ticks:
                tick.set_zorder(3)
            # ax.spines["polar"].set_visible(False)
            ax.set_ylim(*ranges[i])
        # variables for plotting
        self.angle = np.deg2rad(np.r_[angles, angles[0]])
        self.ranges = ranges
        self.ax = axes[0]

    def plot(self, data, *args, **kw):
        sdata = _scale_data(data, self.ranges)
        l = self.ax.plot(self.angle, np.r_[sdata, sdata[0]], *args, **kw)
        # self.ax.set_zorder(2)
        return l

    def fill(self, data, *args, **kw):
        sdata = _scale_data(data, self.ranges)
        self.ax.fill(self.angle, np.r_[sdata, sdata[0]], *args, **kw)



index = ["Carl","Michael","Peter","Louis","Sarah", "Laura","Nicholas"]
df = pd.DataFrame({
    "Spe": pd.Series([89, 83, 70, 60, 30, 49, 28]),
    "Str": pd.Series([69, 53, 30, 20, 10, 29, 48]),
    "Det": pd.Series([82, 44, 79, 39, 20, 10, 85]),
    "Extr": pd.Series([59, 74, 29, 36, 18, 29, 18]),
    "Int": pd.Series([63, 11, 20, 36, 97, 58, 91]),
    "Est": pd.Series([12, 69, 89, 59, 19, 58, 98]),
    "Ape": pd.Series([29, 13, 94, 30, 20, 10, 67]),
})
variables = [k[0] for k in df.iteritems()]


ranges = [(1.,100.),(1.,100.),(1.,100.),(1.,100.),(1.,100.),(1.,100.),(1.,100.)]
fig1 = plt.figure(figsize=(8, 8))
radar = ComplexRadar(fig1, variables, ranges)
lax = []
for i, name  in enumerate(index):
    data=df.iloc[i].values
    l, = radar.plot(data, label=name, zorder=2)
    lax.append(l)
    radar.fill(data,alpha=0.2)

legendax = fig1.add_axes([0.8,0.8,0.1,.1])
legendax.legend(handles = lax, labels=index, loc=3, bbox_to_anchor=(0,0,1,1), bbox_transform=fig1.transFigure )

legendax.axis('off')

plt.show()
