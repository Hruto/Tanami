import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/main.dart';

void main() {
  testWidgets('welcome screen offers Masuk and Daftar', (WidgetTester tester) async {
    await tester.pumpWidget(const TanamiApp());
    await tester.pumpAndSettle();

    expect(find.text('Masuk'), findsOneWidget);
    expect(find.text('Daftar'), findsOneWidget);
    expect(find.textContaining('Temani setiap perjalanan'), findsOneWidget);
  });

  testWidgets('Masuk opens the login form', (WidgetTester tester) async {
    await tester.pumpWidget(const TanamiApp());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Masuk'));
    await tester.pumpAndSettle();

    expect(find.text('Selamat Datang Kembali!'), findsOneWidget);
    expect(find.text('Nama Pengguna'), findsOneWidget);
    expect(find.text('Kata Sandi'), findsOneWidget);
  });
}
