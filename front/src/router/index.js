import { createRouter, createWebHashHistory } from "vue-router";
import AiCenterPage from "../pages/AiCenterPage.vue";
import AiResearchPage from "../pages/AiResearchPage.vue";
import BacktestLabPage from "../pages/BacktestLabPage.vue";
import DashboardPage from "../pages/DashboardPage.vue";
import DataSourcePage from "../pages/DataSourcePage.vue";
import LoginPage from "../pages/LoginPage.vue";
import LobsterFirstClass from "../pages/LobsterFirstClass.vue";
import LobsterRealTimeRadar from "../pages/LobsterRealTimeRadar.vue";
import LobsterWorkshop from "../pages/LobsterWorkshop.vue";
import ProfilePage from "../pages/ProfilePage.vue";
import RegisterPage from "../pages/RegisterPage.vue";
import SettingsPage from "../pages/SettingsPage.vue";

const routes = [
  { path: "/", redirect: "/radar" },
  { path: "/dashboard", name: "dashboard", component: DashboardPage },
  { path: "/radar", name: "radar", component: LobsterRealTimeRadar },
  { path: "/ai-research", name: "ai-research", component: AiResearchPage },
  { path: "/workshop", name: "workshop", component: LobsterWorkshop },
  { path: "/backtest-lab", name: "backtest-lab", component: BacktestLabPage },
  { path: "/strategy-cabin", name: "first-class", component: LobsterFirstClass },
  { path: "/ai-center", name: "ai-center", component: AiCenterPage },
  { path: "/data-sources", name: "data-sources", component: DataSourcePage },
  { path: "/settings", name: "settings", component: SettingsPage },
  { path: "/profile", name: "profile", component: ProfilePage },
  { path: "/login", name: "login", component: LoginPage },
  { path: "/register", name: "register", component: RegisterPage },
  { path: "/lobster_real_time_radar", redirect: "/radar" },
  { path: "/lobster_workshop", redirect: "/workshop" },
  { path: "/lobster_first_class", redirect: "/strategy-cabin" },
];

export default createRouter({
  history: createWebHashHistory(),
  routes,
});
