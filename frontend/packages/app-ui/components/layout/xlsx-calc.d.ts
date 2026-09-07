declare module "xlsx-calc" {
	import type { WorkBook } from "xlsx";

	function calculate(
		workbook: WorkBook,
		options?: { continue_after_error?: boolean; log_error?: boolean },
	): void;

	export default calculate;
}
