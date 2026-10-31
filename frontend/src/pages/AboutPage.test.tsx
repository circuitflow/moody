import { render, screen, within } from "@testing-library/react";
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import type { Evaluation } from "../features/about/evaluation";
import { renderApp } from "../test/render";
import { AboutPage } from "./AboutPage";

const full: Evaluation = {
  deam: {
    n: 400, valence_r: 0.82, arousal_r: 0.84, contrast_r: 0.61, predicted_va_corr: 0.8, rated_va_corr: 0.55,
    loudness_vs_v_minus_a: { model: 0.18, listeners: -0.02 },
    octants: {
      clear: {
        "2026_head": { n: 300, exact: 0.41, within_one: 0.8, mean_angle_error_deg: 47.2 },
        "2007_tree": { n: 290, exact: 0.18, within_one: 0.44, mean_angle_error_deg: 96.8 },
        chance_exact: 0.27,
      },
      clear_radius: 0.25,
      note: "Octants around the neutral point.",
    },
  },
  tags: {
    tracks: 1480, tags_evaluated: 50, macro_roc_auc: 0.77, macro_pr_auc: 0.14,
    best: [{ tag: "christmas", positives: 40, prevalence: 0.03, roc_auc: 0.95, pr_auc: 0.5 }],
    worst: [{ tag: "fun", positives: 30, prevalence: 0.02, roc_auc: 0.6, pr_auc: 0.04 }],
  },
};

function renderAbout(data: Evaluation) {
  const root = createRootRoute();
  const about = createRoute({ getParentRoute: () => root, path: "/", component: () => <AboutPage data={data} /> });
  const stub = (path: string) => createRoute({ getParentRoute: () => root, path, component: () => null });
  const router = createRouter({
    routeTree: root.addChildren([about, stub("/path"), stub("/credits")]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  return render(<RouterProvider router={router} />);
}

test("shows the headline numbers, the 2007 comparison and tag scores", async () => {
  renderAbout(full);
  expect(await screen.findByText("Valence vs listeners")).toBeInTheDocument();
  expect(screen.getByText("0.82")).toBeInTheDocument();
  expect(screen.getByText("41% vs 18%")).toBeInTheDocument();
  expect(screen.getByText(/correlate \+0\.80, against \+0\.55/)).toBeInTheDocument();
  const [octants, tags] = screen.getAllByRole("table");
  expect(within(octants!).getByRole("row", { name: /2007: decision tree 18% 44% 97°/ })).toBeInTheDocument();
  expect(within(octants!).getByRole("row", { name: /Most common octant, always 27%/ })).toBeInTheDocument();
  expect(within(tags!).getAllByRole("row")).toHaveLength(3);
});

test("works before any evaluation has run", async () => {
  renderAbout({ deam: null, tags: null });
  expect(await screen.findByText("No evaluation results yet.")).toBeInTheDocument();
  expect(screen.queryByRole("table")).toBeNull();
});

test("is linked from the navigation", async () => {
  renderApp("/about");
  expect(await screen.findByRole("heading", { name: "About Moody" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "About" })).toBeInTheDocument();
});
