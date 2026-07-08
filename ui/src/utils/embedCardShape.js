// Registers the Vue-backed "embed-card" X6 shape ONCE (import side-effect, module-cached) and
// exports the teleport container that CanvasEditor must render. Split out of canvasX6.js so that
// file stays a pure, Vue-free util (its unit tests import it directly); anything touching Vue /
// @antv/x6-vue-shape lives here and is only pulled in by the canvas component.
//
// Calling getTeleport() flips the library's global "active" flag, which routes every embed node's
// Vue instance through connect() into ONE shared teleport — mounted inside the main app tree — so
// the node components inherit the app context (theme store, the reactive embed store, provides)
// instead of each spinning up an isolated createApp with none of it. See @antv/x6-vue-shape.
import { getTeleport, register } from "@antv/x6-vue-shape";
import EmbedCardNode from "@/components/timeline-notes/EmbedCardNode.vue";
import { EMBED_CARD_SHAPE, EMBED_DEFAULT_HEIGHT, EMBED_DEFAULT_WIDTH } from "./canvasX6.js";

register({
  shape: EMBED_CARD_SHAPE,
  width: EMBED_DEFAULT_WIDTH,
  height: EMBED_DEFAULT_HEIGHT,
  component: EmbedCardNode,
});

export const EmbedTeleport = getTeleport();
