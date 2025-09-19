"""
Log Analysis Tool - Removes repetitive patterns and highlights important events
"""

import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Set, Tuple


class LogAnalyzer:
    """Analyzes container logs to filter noise and highlight important events."""

    def __init__(
        self, noise_threshold: float = 0.8, frequency_threshold: int = 10
    ) -> None:
        # Define patterns to filter out (repetitive noise)
        # Based on industry best practices and common application patterns
        self.noise_patterns = [
            # Health check and monitoring patterns
            r".*(health|healthz|status|ping|metrics|probe).*",
            r".*ELB-HealthChecker.*",
            r".*/health.*",
            r".*/healthz.*",
            r".*/status.*",
            r".*/ping.*",
            r".*/metrics.*",
            r".*heartbeat.*",
            r".*keep.*alive.*",
            # Static asset requests
            r".*\.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)(\?.*)?$",
            r".*/assets/.*",
            r".*/static/.*",
            r".*robots\.txt.*",
            r".*favicon\.ico.*",
            # Debug and trace level logs
            r"^\s*\[(DEBUG|TRACE)\].*",
            r".*\bDEBUG\b.*",
            r".*\bTRACE\b.*",
            # HTTP connection noise
            r".*connection.*pool.*",
            r".*parsed \d+ headers.*",
            r".*incoming body.*",
            r".*flushed \d+ bytes.*",
            r".*bytes written.*",
            r".*bytes read.*",
            # Network and internal requests
            r".*127\.0\.0\.1.*",
            r".*localhost.*",
            r".*internal.*network.*",
            r".*\b10\.\d+\.\d+\.\d+\b.*",
            r".*\b192\.168\.\d+\.\d+\b.*",
            r".*\b172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+\b.*",
            # Metrics and telemetry
            r".*metrics.*endpoint.*",
            r".*telemetry.*",
            r".*prometheus.*",
            r".*grafana.*",
            # Common application noise
            r".*polling.*",
            r".*scheduler.*tick.*",
            r".*cache.*refresh.*",
            r".*session.*cleanup.*",
            r".*garbage.*collect.*",
        ]

        # Define important log levels and keywords
        self.important_levels = {"ERROR", "WARN", "FATAL", "PANIC"}
        self.important_keywords = {
            "Failed",
            "Error",
            "Exception",
            "timeout",
            "refused",
            "expired",
            "invalid",
            "unauthorized",
            "forbidden",
            "subscription",
            "payment",
            "renewal",
            "activation",
        }

        # Advanced noise detection parameters
        self.noise_threshold = noise_threshold  # Frequency ratio to consider as noise
        self.frequency_threshold = (
            frequency_threshold  # Min occurrences for frequency analysis
        )

        # Pattern cache for deduplication
        self.pattern_cache: Dict[str, int] = defaultdict(int)
        self.seen_patterns: Set[str] = set()

        # Dynamic noise patterns discovered during analysis
        self.dynamic_noise_patterns: Set[str] = set()

    def extract_log_template(self, log_line: str) -> str:
        """Extract template from log line by replacing variables with wildcards."""
        # Remove timestamp
        template = re.sub(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", "<TIMESTAMP>", log_line
        )

        # Replace IP addresses first (before general numbers)
        template = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "<IP>", template)

        # Replace phone numbers
        template = re.sub(r"\+\d{10,15}", "<PHONE>", template)

        # Replace UUIDs and long hex strings
        template = re.sub(r"\b[a-f0-9]{32,}\b", "<ID>", template)

        # Replace numbers with wildcards (after IP and phone)
        template = re.sub(r"\b\d+(\.\d+)?\b", "<NUM>", template)

        return template.strip()

    def is_noise(self, log_line: str) -> bool:
        """Check if log line matches noise patterns."""
        # Check against static noise patterns
        for pattern in self.noise_patterns:
            if re.search(pattern, log_line, re.IGNORECASE):
                return True

        # Check against dynamically discovered noise patterns
        template = self.extract_log_template(log_line)
        if template in self.dynamic_noise_patterns:
            return True

        return False

    def detect_frequency_based_noise(self, log_lines: List[str]) -> Set[str]:
        """Detect noise patterns based on frequency analysis."""
        template_counts: Counter[str] = Counter()
        total_lines = len(log_lines)

        if total_lines < self.frequency_threshold:
            return set()

        # Count template occurrences
        for line in log_lines:
            if line.strip():
                template = self.extract_log_template(line)
                template_counts[template] += 1

        # Identify high-frequency patterns as potential noise
        noise_patterns = set()
        for template, count in template_counts.items():
            frequency_ratio = count / total_lines

            # Mark as noise if it occurs too frequently and doesn't contain important keywords
            if (
                frequency_ratio > self.noise_threshold
                and count >= self.frequency_threshold
                and not self.is_important_template(template)
            ):
                noise_patterns.add(template)

        return noise_patterns

    def is_important_template(self, template: str) -> bool:
        """Check if a template contains important information."""
        template_lower = template.lower()

        # Check for important log levels
        for level in self.important_levels:
            if level.lower() in template_lower:
                return True

        # Check for important keywords
        for keyword in self.important_keywords:
            if keyword.lower() in template_lower:
                return True

        return False

    def is_important(self, log_line: str) -> bool:
        """Check if log line contains important information."""
        # Check log level
        for level in self.important_levels:
            if f"{level} " in log_line:
                return True

        # Check keywords
        for keyword in self.important_keywords:
            if keyword.lower() in log_line.lower():
                return True

        return False

    def _prepare_analysis_results(self, log_lines: List[str]) -> Dict[str, Any]:
        """Initialize analysis results and detect dynamic noise patterns."""
        results: Dict[str, Any] = {
            "important_events": [],
            "noise_filtered": 0,
            "patterns": Counter(),
            "errors": [],
            "warnings": [],
            "business_events": [],
            "dynamic_noise_patterns": [],
            "frequency_analysis": {},
        }

        # First pass: detect frequency-based noise patterns
        self.dynamic_noise_patterns = self.detect_frequency_based_noise(log_lines)
        results["dynamic_noise_patterns"] = list(self.dynamic_noise_patterns)

        # Track frequency analysis for insights
        template_counts: Counter[str] = Counter()
        for line in log_lines:
            if line.strip():
                template = self.extract_log_template(line)
                template_counts[template] += 1

        results["frequency_analysis"] = {
            "total_unique_patterns": len(template_counts),
            "most_frequent_patterns": template_counts.most_common(5),
            "patterns_marked_as_noise": len(self.dynamic_noise_patterns),
        }

        return results

    def _categorize_log_line(self, line: str, results: Dict[str, Any]) -> None:
        """Categorize a single log line and update results."""
        # Extract template for pattern analysis
        template = self.extract_log_template(line)
        results["patterns"][template] += 1

        # Categorize important events
        if "ERROR" in line:
            results["errors"].append(line)
        elif "WARN" in line:
            results["warnings"].append(line)

        # Check for business logic events
        if any(
            keyword in line.lower()
            for keyword in ["subscription", "payment", "user", "renewal"]
        ):
            if not self.is_noise(line):
                results["business_events"].append(line)

        # Mark as important if it meets criteria
        if self.is_important(line):
            results["important_events"].append(line)

    def analyze_logs(self, log_lines: List[str]) -> Dict[str, Any]:
        """Analyze log lines and return structured results with advanced noise detection."""
        results = self._prepare_analysis_results(log_lines)

        # Second pass: analyze logs with enhanced noise detection
        for line in log_lines:
            line = line.strip()
            if not line:
                continue

            # Check if it's noise (includes dynamic patterns)
            if self.is_noise(line):
                results["noise_filtered"] += 1
                continue

            # Categorize the log line
            self._categorize_log_line(line, results)

        return results

    def deduplicate_similar_logs(self, log_lines: List[str]) -> List[Tuple[str, int]]:
        """Group similar log lines and return with counts."""
        template_groups = defaultdict(list)

        for line in log_lines:
            template = self.extract_log_template(line)
            template_groups[template].append(line)

        # Return template with count and example
        result = []
        for template, lines in template_groups.items():
            if len(lines) > 1:
                result.append((f"{template} (x{len(lines)})", len(lines)))
            else:
                result.append((lines[0], 1))

        return sorted(result, key=lambda x: x[1], reverse=True)

    def format_analysis_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Format analysis results for API response."""
        return {
            "summary": {
                "noise_patterns_filtered": results["noise_filtered"],
                "important_events_found": len(results["important_events"]),
                "errors_found": len(results["errors"]),
                "warnings_found": len(results["warnings"]),
                "business_events_found": len(results["business_events"]),
                "dynamic_noise_patterns_detected": len(
                    results.get("dynamic_noise_patterns", [])
                ),
            },
            "errors": results["errors"],
            "warnings": results["warnings"],
            "business_events": results["business_events"][
                :20
            ],  # Limit to prevent overflow
            "pattern_analysis": [
                {"pattern": pattern, "count": count}
                for pattern, count in results["patterns"].most_common(10)
            ],
            "frequency_analysis": results.get("frequency_analysis", {}),
            "noise_detection": {
                "static_patterns": len(self.noise_patterns),
                "dynamic_patterns": results.get("dynamic_noise_patterns", []),
                "noise_threshold": self.noise_threshold,
                "frequency_threshold": self.frequency_threshold,
            },
        }
