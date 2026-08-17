package analyzer;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.ReflectionTypeSolver;

import java.io.IOException;
import java.nio.file.*;
import java.util.*;

public class Analyzer {
    public static void main(String[] args) throws IOException {
        if (args.length < 1) {
            System.err.println("Usage: Analyzer <source-root>");
            System.exit(1);
        }

        Path sourceRoot = Paths.get(args[0]).toAbsolutePath();

        CombinedTypeSolver solver = new CombinedTypeSolver(
            new ReflectionTypeSolver(false),
            new JavaParserTypeSolver(sourceRoot)
        );
        StaticJavaParser.getParserConfiguration()
            .setSymbolResolver(new JavaSymbolSolver(solver));

        Map<String, Set<String>> efferent = new HashMap<>();
        Set<String> allPackages = new HashSet<>();

        List<Path> javaFiles = new ArrayList<>();
        try (var stream = Files.walk(sourceRoot)) {
            stream.filter(p -> p.toString().endsWith(".java"))
                  .forEach(javaFiles::add);
        }

        for (Path file : javaFiles) {
            try {
                CompilationUnit cu = StaticJavaParser.parse(file);
                String pkg = cu.getPackageDeclaration()
                    .map(pd -> pd.getNameAsString())
                    .orElse("(default)");
                allPackages.add(pkg);
                efferent.computeIfAbsent(pkg, k -> new HashSet<>());

                cu.getImports().forEach(imp -> {
                    if (imp.isStatic()) return;
                    String importStr = imp.getNameAsString();
                    String importPkg = imp.isAsterisk()
                        ? importStr
                        : importStr.contains(".")
                            ? importStr.substring(0, importStr.lastIndexOf('.'))
                            : importStr;
                    if (!importPkg.equals(pkg)) {
                        efferent.get(pkg).add(importPkg);
                    }
                });
            } catch (Exception e) {
                // skip unparseable files silently
            }
        }

        // Keep only internal packages in efferent sets
        for (String pkg : allPackages) {
            efferent.get(pkg).retainAll(allPackages);
        }

        StringBuilder sb = new StringBuilder("[");
        boolean first = true;
        for (String pkg : allPackages) {
            long ce = efferent.getOrDefault(pkg, Collections.emptySet()).size();
            long ca = allPackages.stream()
                .filter(p -> !p.equals(pkg))
                .filter(p -> efferent.getOrDefault(p, Collections.emptySet()).contains(pkg))
                .count();
            if (!first) sb.append(",");
            first = false;
            sb.append(String.format(
                "{\"package\":\"%s\",\"ce\":%d,\"ca\":%d}",
                pkg.replace("\\", "\\\\").replace("\"", "\\\""), ce, ca
            ));
        }
        sb.append("]");
        System.out.println(sb);
    }
}
