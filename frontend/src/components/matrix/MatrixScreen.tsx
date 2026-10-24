import React, { useCallback, useEffect, useState } from "react";
import { GitMerge } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import {
  calculateApprovalRoute,
  fetchApprovalRules,
} from "../../services/apiClient";
import {
  ApprovalCalculateResponse,
  ApprovalRuleItem,
} from "../../types/api";

export const MatrixScreen: React.FC = () => {
  const { token } = useAuth();
  const [rules, setRules] = useState<ApprovalRuleItem[]>([]);
  const [calcDocType, setCalcDocType] = useState("Приказ о приеме и передаче дел и имущества");
  const [usesModule, setUsesModule] = useState(true);
  const [involvesInfosec, setInvolvesInfosec] = useState(false);
  const [involvesIt, setInvolvesIt] = useState(false);
  const [involvesRegional, setInvolvesRegional] = useState(false);
  const [calcResult, setCalcResult] = useState<ApprovalCalculateResponse | null>(null);

  const loadRules = useCallback(async () => {
    try {
      const list = await fetchApprovalRules(token);
      setRules(list);
      if (list.length > 0) {
        setCalcDocType(list[0].doc_type_name);
      }
    } catch {
      // ignore
    }
  }, [token]);

  useEffect(() => {
    void loadRules();
  }, [loadRules]);

  const handleCalculateMatrix = async () => {
    try {
      const res = await calculateApprovalRoute(
        {
          doc_type: calcDocType,
          uses_module: usesModule,
          involves_infosec_access: involvesInfosec,
          involves_it: involvesIt,
          involves_regional: involvesRegional,
          initiator_department: "Департамент ДОУ",
        },
        token
      );
      setCalcResult(res);
    } catch {
      // ignore
    }
  };

  return (
    <div className="flex-1 h-screen zyricon-stage-bg overflow-y-auto px-6 sm:px-12 py-10">
      <div className="max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-white">Маршруты согласования документов</h1>
          <p className="text-sm text-zinc-400 mt-1">
            Быстрый подбор согласующих подразделений и таблица из 13 правил согласования
          </p>
        </div>

        {/* Route Calculator */}
        <div className="zyricon-glass-card rounded-2xl p-6 space-y-5">
          <div className="flex items-center gap-2.5">
            <GitMerge className="w-5 h-5 text-[#C50337]" />
            <h2 className="text-base font-semibold text-white">Подобрать маршрут согласования</h2>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-end">
            <div className="lg:col-span-5">
              <label className="block text-xs text-zinc-400 mb-1.5">Вид документа</label>
              <select
                value={calcDocType}
                onChange={(e) => setCalcDocType(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-sm text-white"
              >
                {rules.map((r) => (
                  <option key={r.rule_number} value={r.doc_type_name}>
                    Правило № {r.rule_number}: {r.doc_type_name}
                  </option>
                ))}
              </select>
            </div>

            <div className="lg:col-span-5 flex flex-wrap gap-4 text-sm text-zinc-200 pb-1">
              <label className="inline-flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={usesModule}
                  onChange={(e) => setUsesModule(e.target.checked)}
                  className="rounded accent-[#C50337]"
                />
                <span>Модульный шаблон</span>
              </label>
              <label className="inline-flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={involvesInfosec}
                  onChange={(e) => setInvolvesInfosec(e.target.checked)}
                  className="rounded accent-[#C50337]"
                />
                <span>Доступ к ИС (ИБ)</span>
              </label>
              <label className="inline-flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={involvesIt}
                  onChange={(e) => setInvolvesIt(e.target.checked)}
                  className="rounded accent-[#C50337]"
                />
                <span>ИТ-проект (ДИТ)</span>
              </label>
              <label className="inline-flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={involvesRegional}
                  onChange={(e) => setInvolvesRegional(e.target.checked)}
                  className="rounded accent-[#C50337]"
                />
                <span>Участие РО</span>
              </label>
            </div>

            <div className="lg:col-span-2">
              <button
                onClick={() => void handleCalculateMatrix()}
                className="w-full py-2.5 px-4 rounded-xl bg-[#C50337] hover:opacity-90 text-sm font-semibold text-white transition"
              >
                Рассчитать
              </button>
            </div>
          </div>

          {calcResult && (
            <div className="p-5 rounded-xl bg-[#111115] border border-white/[0.14] space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <span className="font-semibold text-white">
                  Правило № {calcResult.rule_number} — {calcResult.doc_type_name}
                </span>
                <span className="text-zinc-300">
                  Подписант: <strong className="text-white">{calcResult.signatory}</strong>
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
                {calcResult.stages.map((st) => (
                  <div
                    key={st.order}
                    className="p-3.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-xs space-y-1"
                  >
                    <div className="font-mono text-zinc-400">Этап {st.order}</div>
                    <div className="font-semibold text-white text-sm">{st.department}</div>
                    <div className="text-zinc-400">{st.role_name}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* All 13 Rules Table */}
        <div className="zyricon-glass-card rounded-2xl p-6 space-y-4">
          <h3 className="text-base font-semibold text-white">
            Таблица правил визирования ({rules.length})
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-white/[0.08] text-zinc-400 text-xs">
                  <th className="py-2.5 pr-2">№</th>
                  <th className="py-2.5 px-2">Вид документа</th>
                  <th className="py-2.5 px-2">Юр. служба</th>
                  <th className="py-2.5 px-2">ДОУ</th>
                  <th className="py-2.5 px-2">Кадры</th>
                  <th className="py-2.5 px-2">Условия (ИБ / ИТ / РО)</th>
                  <th className="py-2.5 pl-2">Подписант</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.06]">
                {rules.map((r) => (
                  <tr key={r.rule_number} className="hover:bg-white/[0.02]">
                    <td className="py-3 pr-2 font-mono text-zinc-300">#{r.rule_number}</td>
                    <td className="py-3 px-2">
                      <div className="font-medium text-white">{r.doc_type_name}</div>
                      {r.condition_description && (
                        <div className="text-xs text-zinc-400 mt-0.5">{r.condition_description}</div>
                      )}
                    </td>
                    <td className="py-3 px-2">{r.requires_legal ? "Да" : "Модуль"}</td>
                    <td className="py-3 px-2">{r.requires_dou ? "Да" : "—"}</td>
                    <td className="py-3 px-2">{r.requires_hr ? "Да" : "—"}</td>
                    <td className="py-3 px-2 font-mono text-xs text-zinc-300">
                      ИБ:{r.requires_infosec} | ИТ:{r.requires_it} | РО:{r.requires_regional}
                    </td>
                    <td className="py-3 pl-2 text-white font-medium">{r.signatory}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
