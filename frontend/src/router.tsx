import {
  createHashHistory,
  createRootRoute,
  createRoute,
  createRouter,
  type RouterHistory,
} from "@tanstack/react-router";
import { Shell } from "./components/Shell";
import { MapPage } from "./pages/MapPage";
import { ListPage } from "./pages/ListPage";
import { TrackPage } from "./pages/TrackPage";

const rootRoute = createRootRoute({ component: Shell });
const mapRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: MapPage });
const listRoute = createRoute({ getParentRoute: () => rootRoute, path: "/list", component: ListPage });
const trackRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/track/$trackId",
  component: TrackPage,
});

const routeTree = rootRoute.addChildren([mapRoute, listRoute, trackRoute]);

/** Hash history so deep links work on static hosting (GitHub Pages). */
export function createAppRouter(history: RouterHistory = createHashHistory()) {
  return createRouter({ routeTree, history });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
