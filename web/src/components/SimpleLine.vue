<script setup lang="ts">
import { ref, onMounted, watch, type Ref } from "vue";
import { nextTick } from "vue";

import VChart from "vue-echarts";
import type { ComposeOption } from "echarts/core";
import type { LineSeriesOption } from "echarts/charts";
import type {
  TitleComponentOption,
  TooltipComponentOption,
  ToolboxComponentOption,
  LegendComponentOption,
  GridComponentOption,
} from "echarts/components";

type EChartsOption = ComposeOption<
  | LineSeriesOption
  | TitleComponentOption
  | TooltipComponentOption
  | ToolboxComponentOption
  | LegendComponentOption
  | GridComponentOption
>;

import { use } from "echarts/core";
import { SVGRenderer, CanvasRenderer } from "echarts/renderers";
// normally, only a single chart type is needed
// unless toolbox allows to switch types (like here ...)
import { LineChart } from "echarts/charts";
import {
  TitleComponent,
  TooltipComponent,
  ToolboxComponent,
  LegendComponent,
  GridComponent,
} from "echarts/components";


const props = defineProps({
  /* Add your props here */
  dataUrl: {
    type: String,
    required: true,
  },
  title: {
    type: String,
    default: "Chart Title",
  },
  // optional X axis label
  labelX: {
    type: String,
    default: "Date",
  },
  // optional Y axis label
  labelY: {
    type: String,
    default: "Cnt/min",
  }
});

const chartOptions: Ref<EChartsOption> = ref({
        title: {
        text: props.title,
        left: "center",
      },
      tooltip: {
        trigger: "axis",
        axisPointer: {
          type: "cross",
        },
      },
      toolbox: {
        feature: {
          saveAsImage: {},
          dataZoom: {
            yAxisIndex: "none",
          },
          restore: {},
        },
      },
      legend: {
        data: ["Sensor Data"],
        top: 30,
      },
      grid: {
        left: "10%",
        right: "10%",
        bottom: "15%",
      },

});

const theChart = ref<typeof VChart | null>(null);
const dataLoaded = ref(false);

watch(
  () => props.dataUrl,
  async (newUrl, oldUrl) => {
    if (newUrl !== oldUrl) {
      const data = await loadData(newUrl);
      dataLoaded.value = true;
      await nextTick();
      await showData(data);
    }
  }
);


const loadData = async (url: string) => {
  try {
    console.log("Fetching: ", url);
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    if (data && data.series && data.series.length > 0) {
      return data.series;
    } else {
      throw new Error("Invalid data format");
    }
  } catch (error) {
    console.error("Failed to load chart data for ", props.dataUrl, ": ", error);
    return [];
  }
};

const showData = async (data: any) => {
  if (!theChart.value) {
    console.error("Chart instance not ready");
    return;
  }
  try {
    if (theChart.value) await theChart.value.clear();
    if (!data || !Array.isArray(data) || data.length === 0) {
      dataLoaded.value = false;
      return;
    }

    // convert input to [timestamp, value] pairs (echarts time axis accepts ISO strings)
    const seriesData = data.map((row) => {
      return [row.timestamp, row.counts_per_minute];
    });

    chartOptions.value.title! = { text: props.title, left: "center" };

    // set up a single line series (adjust options as needed)
    chartOptions.value.xAxis = {
      type: "time",
      name: props.labelX,
      axisLabel: { rotate: 30 },
    };
    chartOptions.value.yAxis = {
      type: "value",
      name: props.labelY,
      min: "dataMin",
      // you can add formatter here if needed
    };

    chartOptions.value.series = [
      {
        name: "Sensor Data",
        type: "line",
        smooth: true,
        showSymbol: false,
        //sampling: "lttb",
        data: seriesData.map(([ts, val]) => [ts, val != null ? Math.round(Number(val)) : val]),
        lineStyle: { width: 2 },
        //areaStyle: {},
      },
    ];

    //chartOptions.value.title.text = title || props.title;    
    await theChart.value.setOption(chartOptions.value)

  } catch (error) {
    console.error("Failed to load chart data for ", props.dataUrl, ": ", error);
  }
};

use([
  CanvasRenderer,
  SVGRenderer,
  LineChart,
  TitleComponent,
  TooltipComponent,
  ToolboxComponent,
  LegendComponent,
  GridComponent,
]);

const onChartReady = () => {
  console.log("Chart is ready");
};

onMounted(async () => {
  console.log("SimpleLine mounted, loading data from ", props.dataUrl);
  const data = await loadData(props.dataUrl);
  console.log("Data loaded:", data.length, "points");
  dataLoaded.value = true;
  await nextTick();
  await showData(data);
  console.log("Chart displayed");
});

</script>

<template>
  <v-chart class="timeseries" v-if="dataLoaded" ref="theChart" :option="chartOptions" 
    :init-options="{ renderer: 'canvas' }" autoresize  @ready="onChartReady">
  </v-chart>
</template>

<style scoped>
.timeseries {
  width:100%;
  height:100%;
  display: block;
  justify-content: center;
  align-items: center;
}
</style>
